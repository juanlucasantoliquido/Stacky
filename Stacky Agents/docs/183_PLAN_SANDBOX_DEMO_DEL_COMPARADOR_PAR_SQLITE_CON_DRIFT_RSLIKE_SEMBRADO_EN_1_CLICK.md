# Plan 183 — Sandbox de demostración del comparador: par sqlite con drift RS-like, sembrado en 1 click, ciclo completo probable sin credenciales

**Estado:** CRITICADO (v2, 2026-07-18, juez `criticar-y-mejorar-plan`). La v1 (PROPUESTO 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`) fue **RECHAZADA** por DOS bloqueantes: C1 — el sandbox entero no arranca: el seed no guardaba password y `open_engine` la EXIGE para todo engine (la cita "tolera credencial ausente `:141`" era de `test_connection`, no de la cadena real `get_credential:216-217` → `open_engine:88-94`); C2 — el KPI-5 era imposible: con el DDL v1 ningún ITEM del diff queda con severity `info` (el único change info convivía con un danger en el mismo item). Esta v2 los corrige in place y queda lista para `implementar-plan-stacky`.

**Serie:** Comparador de BD — capa 8 (adopción y verificabilidad; multiplicador de smokes de toda la serie). Relación con 157/176/178-182: §2bis. El carril que usa ya existe y hasta lo anuncia el propio motor: el mensaje de `_validate_engine` dice literal "(reservado a tests/demo)" (`services/dbcompare_registry.py:84-86`) — este plan es la mitad "demo" de esa reserva, con CERO cambios al motor.

## Versión: v1 -> v2 (2026-07-18, criticar-y-mejorar-plan)

**CHANGELOG v1 -> v2:**
- **C1 (BLOQUEANTE, resuelto):** la v1 descartaba el password dummy en keyring (§7 v1) citando `dbcompare_engine.py:141` — pero esa línea es el fallback COSMÉTICO de `test_connection`; la cadena real es `open_engine:88-94` → `get_credential` (`dbcompare_registry.py:203-218`), que retorna `None` si NO hay password en keyring (`:216-217`) o si keyring no está disponible (`:210`) ⇒ `open_engine` lanza "credencial faltante" TAMBIÉN para sqlite ⇒ sin password sembrada, el sandbox no puede tomar NI UN snapshot y KPI-1/2/5/6 mueren. La evidencia correcta del repo es el fixture del 122: `reg.set_password("test-snap", "unused")` (`tests/test_plan122_dbcompare_snapshot.py:66`). Fix: el seed guarda `set_password(alias, "demo")` por alias (dummy — la URL sqlite no la usa, `dbcompare_engine.py:74`); el delete ya la limpia (`delete_environment` → `clear_password`, `dbcompare_registry.py:175`); sin keyring disponible el seed falla con error claro y accionable (mismo límite que el alta normal de passwords, `api/db_compare.py:120-127`) — riesgo R11 nuevo; §7 reescrito con la evidencia correcta; test nuevo del password sembrado.
- **C2 (BLOQUEANTE, resuelto):** KPI-5 v1 asserta `{it["severity"]} == {"info","warn","danger"}` sobre ITEMS — imposible con el DDL v1: la severidad de un item con changes es el MAX (`_item`, `dbcompare_diff.py:231-236`) y el único change `info` (default de `RTABL.ACTIVO`) convive con `column_nullable_tightened` (danger) e `index_added` (warn) en el MISMO item ⇒ items = {warn, danger} solamente. Fix: tabla nueva `RESTILO` en AMBOS lados cuya ÚNICA diferencia es el DEFAULT (`'AZUL'` vs `'ROJO'`) ⇒ item `changed` con un solo change `column_default_changed` ⇒ severity `info`; fila nueva en §4.3; KPI-5 reescrito (items {info,warn,danger} + kinds de changes contra la lista).
- **C3 (IMPORTANTE, resuelto):** DELETE con corrida activa del par demo: los `.db` pueden estar lockeados por la conexión sqlite del run (Windows file lock) ⇒ `shutil.rmtree` lanza `PermissionError` ⇒ 500 no controlado. Fix: el rmtree va en try/except `OSError` → la API responde 409 declarado (`{"ok": false, "error": "archivos del sandbox en uso (¿corrida activa?); reintentá al terminar"}`); el estado intermedio (desregistrado sin archivos borrados) es detectable por `status` y el delete es re-ejecutable; test con monkeypatch de `shutil.rmtree`; nota: el run en curso termina en `error` inofensivo al perder los aliases (política existente del motor).
- **C4 (IMPORTANTE, resuelto):** el prefijo `test-demo-` no estaba declarado como namespace reservado y el seed PISABA sin guard un alias homónimo creado a mano (`upsert_environment` reemplaza el record, `dbcompare_registry.py:159-160`). Fix: guard del seed — si existe un alias `test-demo-*` cuyo `database` NO apunta dentro de `demo/` ⇒ aborta con error claro SIN tocar nada (test nuevo); el prefijo queda declarado RESERVADO del sandbox (§3 + description de la flag).
- **C5 (IMPORTANTE, resuelto):** faltaba el verbo "Apagar la flag" en §9.2: con OFF post-seed los endpoints demo dan 403 pero los aliases/archivos PERSISTEN y siguen usables por el motor normal (decisión ahora explícita: es correcto — el motor es agnóstico; para quitarlos: re-encender la flag y "Quitar demo", o la baja normal de ambientes `DELETE /environments/<alias>`, `api/db_compare.py:101-108`). Fila nueva en §9.2 + riesgo R12.
- **C6 (IMPORTANTE, resuelto) [ADICIÓN ARQUITECTO]:** estado roto (archivos borrados a mano con aliases vivos, o seed interrumpido) era detectable por `status` pero el panel v1 mostraba "demo activo" sano. Fix: `demoPanelState` gana el estado **`demo-broken`** (`registered` XOR `files_present`) con CTA "Re-sembrar" (el seed ya repara) — reparación en 1 click, coherente con el propósito del plan; test del estado nuevo.
- **C7 (MENOR, resuelto):** §2bis gana la tabla de los 4 puntos de montaje ACUMULADOS de la serie en `DbComparePage.tsx` (178 radar, 180 coverage, 181 no toca la página, 183 demo, 176 triage) con sus anchors — el del 178 ("antes del wizard, después del header") y el del 183 (entre `missingDrivers:129-139` y `DbCompareSettingsSection:141` — anchor verificado) pueden quedar adyacentes: regla "conservar todos".
- **C8 (MENOR, resuelto):** notas de coherencia con el 157 (papel): su `CredentialWarningBanner` no debe marcar "sin contraseña" a ambientes sqlite; y el alcance del fix del wizard se declara: aplica a CUALQUIER ambiente sqlite del carril `test-*` (también los creados a mano), no solo a los demo — semánticamente correcto en ambos casos.
- **C9 (MENOR, resuelto):** R5 explícito: los runs demo CONSUMEN slots de la retención compartida (`_MAX_RUNS_KEPT=100`) y pueden acortar el histórico real — mitigado por "Quitar demo" y declarado.
- Verificaciones del juez A FAVOR del autor (2026-07-18): KPI-2 redefinido honestamente a determinismo observable (content_hash + SELECTs, NO bytes del `.db`) — la lección de la serie bien aplicada; los 5 microhunks del wizard citan líneas EXACTAS (verificadas: `wizardLogic.ts:39-41,61-66`, `CompareWizard.tsx:39,85-86,95`); el anchor del panel es exacto (`DbComparePage.tsx:129-141`); `_diff_by_signature` (`dbcompare_diff.py:144-163`) confirma la dirección `index_added` para "solo en origen" (acá NO hay inversión); el gotcha de dirección de columnas (added/removed invertidos vs docstring) estaba correctamente asserted-against-reality en §4.3; los counts del data-diff (1+2+1 y 1) son exactos fila por fila; el guard doble del delete es sólido; "todo por código" anti-PyInstaller correcto; claims negativos verificables.

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Que cualquier operador pruebe el ciclo COMPLETO del comparador (registrar→snapshot→diff→drill-down→data-diff→scripts) en menos de un minuto y SIN credenciales reales, sembrando con 1 click un par de ambientes sqlite de ejemplo (`test-demo-dev` → `test-demo-test`) con drift realista del dominio RS que ejercita el catálogo de severidades del diff — y que ese sandbox vuelva ejecutables los smokes manuales de la serie (176/178/179/181/182) que hoy quedan eternamente pendientes por pedir "2 ambientes registrados".

### 1.2 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | **Seed 1-click E2E:** `seed_demo_environments()` deja 2 ambientes registrados (`test-demo-dev`, `test-demo-test`, engine sqlite) CON password dummy en keyring (fix C1 — la cadena real `open_engine→get_credential` la exige), y un `create_run` real del par termina `done` con `items` no vacíos, y `data-candidates` lista `RPARAM` comparable y `RLOG` no comparable (sin PK). | `tests/test_plan183_demo_e2e.py::test_ciclo_completo_sqlite` |
| KPI-2 | **Re-seed determinista (observable por el motor):** tras `seed` ×2, `take_snapshot` de cada alias produce el MISMO `content_hash` que tras el primer seed, y `SELECT *` ordenado de cada tabla demo es idéntico. (NO se promete igualdad byte a byte del archivo `.db` — límite declarado: sqlite escribe metadatos internos propios; el determinismo que importa es el que ve el motor, que hashea el esquema canónico, `dbcompare_snapshot.py:205-207`.) | `tests/test_plan183_demo_seed.py::test_reseed_determinista` |
| KPI-3 | **DELETE jamás sale del sandbox (test negativo):** con un archivo señuelo fuera de `demo/` y un ambiente real fake registrado, `delete_demo()` borra SOLO `data_dir()/db_compare/demo/` y desregistra SOLO aliases `test-demo-*`; el señuelo y el ambiente real quedan intactos; un alias que no empiece con `test-demo-` JAMÁS se desregistra por esta vía. | `tests/test_plan183_demo_lifecycle.py::test_delete_acotado_guard_doble` |
| KPI-4 | Con `STACKY_DB_COMPARE_DEMO_ENABLED=false` (o master 122 OFF): endpoints nuevos 403, cero UI nueva (panel `null`), suite dbcompare preexistente verde sin editarla. | `tests/test_plan183_demo_api.py::test_403_flags_off` |
| KPI-5 | **Drift cubre el catálogo (fix C2):** el diff real del par demo produce ITEMS cuyas severidades son EXACTAMENTE `{"info","warn","danger"}` (el item `info` lo garantiza `RESTILO`, cuya única diferencia es un DEFAULT) y los kinds de los CHANGES incluyen la lista esperada de §4.3 (asserteada contra los kinds reales de `_KIND_SEVERITY`, `dbcompare_diff.py:28-52`). | `tests/test_plan183_demo_e2e.py::test_catalogo_severidades` |
| KPI-6 | **Smokes de ≥4 planes ejecutables:** el mapa §2ter deja 176/178/179/181/182 con pasos concretos contra el sandbox; la base común (run `done` con schema-diff no vacío + data-diff de `RPARAM` con insert+update+delete) está probada por test. | mapa §2ter + `tests/test_plan183_demo_e2e.py::test_base_comun_smokes` |
| KPI-7 | **sqlite sin contraseña seleccionable en el wizard:** `selectableTargets`/`canLaunch` habilitan ambientes `engine=="sqlite"` sin password (regla nueva), sin cambiar el comportamiento para sqlserver/oracle; el test preexistente `__tests__/wizardLogic.test.ts` queda verde sin editarlo. (Nota fix C1: los ambientes DEMO igual llevan password dummy en keyring para el MOTOR; esta regla de UI cubre además cualquier sqlite `test-*` manual sin password.) | `frontend/src/components/dbcompare/__tests__/wizardLogicDemo.test.ts` + corrida del preexistente |

---

## 2. Por qué ahora / gap

1. **La fricción es real y transversal**: HOY nada del comparador es probable sin registrar 2 BDs reales con credenciales. Los smokes manuales de TODA la serie piden exactamente eso ("2 ambientes registrados", "BD real", "ambiente de prueba") — 176 F8, 178 F8, 179 F5, 181 F6, 182 F4 — y por eso quedan pendientes para siempre. Este plan los desbloquea de una vez (§2ter).
2. **El carril ya existe y es casi gratis**: el registry acepta `engine="sqlite"` SOLO para alias `test-*` (`dbcompare_registry.py:80-89`, mensaje "(reservado a tests/demo)" en `:84-86`); el engine arma la URL sqlite con `database` = path del archivo (`dbcompare_engine.py:73-74`) y no exige driver externo (`:96`). **Cadena de credencial (fix C1, la verdad completa):** `open_engine` exige `get_credential(alias) != None` (`dbcompare_engine.py:88-94`) y `get_credential` exige keyring disponible Y password guardada (`dbcompare_registry.py:210,216-217`) — por eso el seed guarda una password dummy `"demo"` (nunca usada en la URL sqlite), EXACTAMENTE como hace el fixture sqlite del 122 (`tests/test_plan122_dbcompare_snapshot.py:66`: `set_password("test-snap", "unused")`). El snapshot/diff/data-diff/scripts ya corren sobre sqlite en los tests del 122/125/126. CERO cambios al motor.
3. **Onboarding casi nulo — la frase literal del mandato**: primer contacto con el comparador = 1 click y ya hay un diff rico en pantalla para explorar. Es la diferencia entre "instalé Stacky y vi una pantalla vacía que pide credenciales" y "vi el producto funcionando".
4. **Claims negativos (con comando):** no existe hoy ningún seeder/demo del comparador — `grep -il "demo|sample|seed"` sobre `backend/services/dbcompare*.py` → **1 hit**: `dbcompare_registry.py:85` (el TEXTO "(reservado a tests/demo)" del mensaje de error — no hay código de demo); sobre `backend/api/db_compare.py` → **0 hits**; sobre `backend/api/` → 8 archivos de OTROS dominios — ninguno relacionado al comparador. El prefijo `test-demo-` no colisiona con nada: `grep -r "test-demo"` sobre todo el repo → **0 hits**.

---

## 2bis. Relación con 157 / 176 / 178 / 179 / 180 / 181 / 182

| Plan | Archivos que toca | Intersección con 183 |
|---|---|---|
| 157 (config UX) | `EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `dbcompare_config_import.py` (nuevo), `MigrationPanel.tsx` | NINGUNA de archivos. **Complementariedad declarada**: 157 = registrar BDs REALES más fácil; 183 = probar SIN BDs. **Notas de coherencia (fix C8):** si el 157 se implementa, su `CredentialWarningBanner` NO debe marcar "sin contraseña" a ambientes `engine=="sqlite"` (heredar la regla §3.2); y su wizard de alta no necesita cambios para el demo (el seed registra por servicio) |
| 176 (triage/gates) | `api/db_compare.py`, `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts`, `DataParitySection.tsx` | `DbComparePage.tsx` (1 hunk) + `endpoints.ts` (append) |
| 178 (radar) / 180 (repo bridge) | sus módulos nuevos + `DbComparePage.tsx` + `endpoints.ts` | ídem: solape solo en los 2 puntos de montaje compartidos |
| 179 (snapshot v2) | `dbcompare_snapshot.py`, `dbcompare_diff.py` | NINGUNA |
| 181 (masking) | `dbcompare_masking.py` (nuevo), `get_run_route`, `list_runs` (1 línea), `DataParitySection.tsx` | NINGUNA |
| 182 (MERGE) | `dbcompare_scripts.py` | NINGUNA |
| **183 (este)** | NUEVOS: `services/dbcompare_demo.py`, `api/db_compare_demo.py`, `DemoSandboxPanel.tsx`, `demoLogic.ts`, `__tests__/demoLogic.test.ts`, `__tests__/wizardLogicDemo.test.ts`, 4 tests backend. EDITADOS: `api/__init__.py` (2 líneas), `DbComparePage.tsx` (1 import + 1 JSX), `endpoints.ts` (append final), `dbcompare.module.css` (append), `wizardLogic.ts` (2 microhunks), `CompareWizard.tsx` (3 microhunks), `harness_flags.py`, `config.py`, `test_harness_flags_requires.py`, runners sh/ps1 | — |

**Nota sobre `wizardLogic.ts`/`CompareWizard.tsx`** (archivos que NINGÚN otro plan de la serie declara tocar — colisión nula): son la única edición "de motor de UI" del plan y existe por un hallazgo verificado — el gate de contraseña (§3.2).

**Anchors ACUMULADOS de la serie en `DbComparePage.tsx` (fix C7 — guía para quien mergee varios planes):**

| Plan | Punto de montaje declarado | Anchor |
|---|---|---|
| 183 (este) | `<DemoSandboxPanel .../>` | entre el bloque `missingDrivers` (`:129-139`) y `<DbCompareSettingsSection />` (`:141`) — verificado |
| 178 | `<EnvironmentRadar .../>` | después del header, ANTES del bloque del wizard (`:145`) |
| 180 | `<RepoCoveragePanel .../>` | dentro del bloque results, tras `DataParitySection` |
| 176 | triage/gates | dentro del bloque results |

Regla de merge: los anchors del 183 y el 178 pueden quedar ADYACENTES (ambos en la zona post-header) — conservar TODOS los elementos, orden visual final = demo → radar → settings → timeline → wizard/results; tras cada merge `npx tsc --noEmit` + grep de cada componente esperando 1 aparición.

---

## 2ter. Mapa de smokes desbloqueados (el multiplicador de valor)

Base común (probada por KPI-6): `seed` → comparar `test-demo-dev` → `test-demo-test` (modo fresco) → run `done` con diff rico + data-diff de `RPARAM`.

| Plan | Smoke que hoy está bloqueado | Pasos contra el sandbox (1-3 líneas) |
|---|---|---|
| 176 (cuando se implemente) | Triage/gates/claves naturales piden un run real con ítems y una tabla sin PK | Seed → comparar par demo → triage sobre los ~8 ítems; `RLOG` (sin PK) es el caso de claves naturales; los gates read-only corren contra sqlite local |
| 178 (cuando se implemente) | Radar/matriz/baseline/tendencia piden runs persistidos y 2+ ambientes | Seed → correr el compare demo 2-3 veces → la matriz muestra el par con estado rojo (hay danger); pinnear baseline de `test-demo-dev` desde sus snapshots; la tendencia grafica las corridas |
| 179 (cuando se implemente) | Snapshot v2 pide "BD sqlserver real" para ver `type_detail` | Seed → tomar snapshot de `test-demo-dev` con la flag v2 ON → el JSON trae `type_detail` con `precision=10, scale=2` en `RTABL.MONTO_TOPE` (sqlite refleja el tipo declarado `NUMERIC(10,2)`) |
| 181 (cuando se implemente) | Masking pide "tabla con columna de password real" | Seed → data-diff de `RCREDENCIAL` (columna `PASSWORD`, detector por NOMBRE) y de `RPARAM` fila `CONN_LEGACY` (valor `Server=...;Password=...;`, detector por VALOR) → grid enmascarado; revelar con 1 click |
| 182 (cuando se implemente) | MERGE pide BD real y "ejecutar dos veces" | Seed → data-diff de `RPARAM` → generar scripts → `03_datos/` trae el upsert sqlite de 1 línea por fila; el operador puede hasta ejecutar las piezas DML dos veces contra SU archivo sqlite demo sin riesgo (los backups del bundle son single-shot — doctrina 182) |
| 157 | — | No mapeado: sus smokes son de conexión a BDs REALES (import web.config, credenciales); complementario por diseño (§2bis) |

---

## 3. Principios y guardarraíles

- **CERO cambios al motor**: registro vía la API PÚBLICA del registry (`upsert_environment`, `dbcompare_registry.py:114-164` — la MISMA que usa el endpoint de alta, `api/db_compare.py:85-95`; `set_password` — la misma vía que el endpoint de password; `delete_environment` `:167-175` — la misma que `:101-108`). Snapshot/diff/runs/data/scripts NO se tocan.
- **HITL**: seed y delete son SIEMPRE por click del operador; nada corre solo; el DELETE pide confirmación en la UI y además está doblemente guardado en backend (§3.1).
- **Aislamiento**: los aliases demo usan el carril sqlite `test-*` ⇒ JAMÁS una conexión de red; los archivos viven en `data_dir()/db_compare/demo/`; el registro es el normal (`db_compare/environments.json`, `dbcompare_registry.py:27,37-38`) — visible y transparente para el operador. **El prefijo `test-demo-` es NAMESPACE RESERVADO del sandbox (fix C4)**: el seed rechaza adoptarlo si un alias homónimo apunta fuera de `demo/`, y el delete solo desregistra ese prefijo.
- **Password dummy en keyring (fix C1 — obligatoria, con evidencia):** `get_credential` retorna `None` sin password (`dbcompare_registry.py:216-217`) y `open_engine` lanza ante `None` (`dbcompare_engine.py:88-94`) ⇒ el seed guarda `set_password(alias, "demo")` (la URL sqlite NO la usa, `:74` — es un requisito del contrato del registry, igual que el `username="demo"`). Precedente literal del repo: `tests/test_plan122_dbcompare_snapshot.py:66`. El delete la limpia vía `delete_environment→clear_password` (`:175`). Sin keyring disponible: el seed falla con error claro (R11) — el MISMO límite que el alta normal de contraseñas (`api/db_compare.py:120-127` responde 503).
- **Runs demo en el historial — decisión con evidencia**: los runs del par demo son runs normales y se muestran como `test-demo-dev → test-demo-test` en la timeline (`RunsTimeline.tsx:30` renderiza `{run.source_alias} → {run.target_alias}`) — el prefijo del alias es autoexplicativo, NO se necesita marcador extra; los recicla la retención normal (`_MAX_RUNS_KEPT = 100`, `dbcompare_runs.py:32`; snapshots `_MAX_SNAPSHOTS_PER_ALIAS = 20`, `dbcompare_snapshot.py:31`) y CONSUMEN slots de esa retención compartida (fix C9 — declarado en R5).
- **Todo por código, cero data files**: el seed genera esquema y filas con `sqlite3` de la stdlib (evita el gotcha PyInstaller de collect-data: no hay archivos `.db`/`.sql` empaquetados que el freeze pueda perder; `sqlite3` viene con Python).
- **Mono-operador sin auth real**: nada de RBAC.
- **3 runtimes**: feature de panel (Flask + React, sin LLM): idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro; ni siquiera depende de drivers (sqlite es stdlib — `dbcompare_engine.py:96` lo exime del chequeo de drivers).
- **Flag**: `STACKY_DB_COMPARE_DEMO_ENABLED`, bool, **default ON** — justificación literal: nada corre solo (seed/delete son por click), sqlite es stdlib (cero prerequisitos de red/drivers), los aliases demo jamás tocan una BD real ⇒ NINGUNA de las 4 excepciones duras aplica. Registro completo del patrón: `_CURATED_DEFAULTS_ON` (`harness_flags.py:310`), `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`), `requires="STACKY_DB_COMPARE_ENABLED"` (plano, profundidad 1), arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120,183-185`), default en `config.py` (idioma `:119-133`), `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py`.
- **Tests por archivo** con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`; los 4 `tests/test_plan183_*.py` registrados en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20` + espejo `.ps1`). Frontend sin RTL/jsdom: lógica en `.ts` puros con vitest por archivo (los tests dbcompare viven en `frontend/src/components/dbcompare/__tests__/` — patrón verificado) + `npx tsc --noEmit`; CERO `style={{...}}`.

### 3.1 Guard doble del DELETE (regla literal)

`delete_demo()` ejecuta EXACTAMENTE dos operaciones, cada una con su guard independiente:

1. **Desregistro**: itera `list_environments()` y llama `delete_environment(alias)` SOLO si `alias.startswith("test-demo-")` — cualquier otro alias es INALCANZABLE por esta función (guard 1: prefijo). (`delete_environment` limpia también la password del keyring, `:175`.)
2. **Borrado de archivos**: `demo_root = (data_dir() / "db_compare" / "demo").resolve()`; para CADA path a borrar, verificación `path.resolve().is_relative_to(demo_root)` ANTES de tocarlo; luego `shutil.rmtree(demo_root)` del directorio completo y nada más (guard 2: contención de path canónico). Si la verificación falla, la operación aborta con excepción SIN borrar nada. **El rmtree va en try/except `OSError` (fix C3):** archivos lockeados por una corrida activa (Windows) ⇒ la función reporta el fallo SIN 500 (la API responde 409 declarado) y el delete queda re-ejecutable; el estado intermedio (desregistrado + archivos presentes) es visible por `status`.

Los snapshots (`db_compare/snapshots/test-demo-*/`), runs y bundles históricos del par demo NO se borran (decisión v1 de mínima superficie destructiva): los recicla la retención normal del motor; `GET /demo/status` los reporta para transparencia.

### 3.2 Hallazgo verificado: el gate de contraseña del wizard (y su fix mínimo)

El backend NO usa contraseña en la URL sqlite (`dbcompare_engine.py:73-74`; el requisito de keyring es del CONTRATO del registry — §3, fix C1 — y el seed lo satisface). Pero la UI exige `has_password` para TODO engine: `CompareWizard.tsx:39` (`if (!env.has_password) return;` en `selectSource`), `wizardLogic.ts:39-41` (regla de `selectableTargets`: "sin password ⇒ deshabilitado") y `wizardLogic.ts:61-66` (`canLaunch` chequea ambos lados). Con el fix C1 los ambientes DEMO tienen password dummy y pasarían igual — pero la regla de UI sigue siendo semánticamente incorrecta para sqlite (un `test-*` manual sin password quedaría bloqueado sin razón). Fix mínimo (5 microhunks, líneas verificadas, archivos que ningún otro plan toca):

- `wizardLogic.ts:39` → `if (!e.has_password && e.engine !== "sqlite") {`
- `wizardLogic.ts:61,64` → `if (!source.has_password && source.engine !== "sqlite")` / ídem target.
- `CompareWizard.tsx:39` → `if (!env.has_password && env.engine !== "sqlite") return;`
- `CompareWizard.tsx:85-86,95` → las 3 señales visuales (`aria-disabled`, `title`, "⚠ sin contraseña") ganan la misma condición `&& env.engine !== "sqlite"`.

Alcance declarado (fix C8): la regla aplica a CUALQUIER ambiente `engine=="sqlite"` (solo existen en el carril `test-*` por el registry) — correcto también para sqlite manuales. Sin cambio alguno para sqlserver/oracle. El test preexistente `__tests__/wizardLogic.test.ts` se corre SIN editar (perímetro §9: si fijara "sqlite sin password ⇒ disabled", sería hallazgo bloqueante de diseño — lo esperable es que sus fixtures sean sqlserver/oracle); la regla nueva se cubre en un archivo NUEVO `__tests__/wizardLogicDemo.test.ts`.

---

## 4. Contrato del seed (esquema y drift EXACTOS)

### 4.1 Ubicación, registro y credencial

- Archivos: `data_dir()/db_compare/demo/demo_dev.db` y `demo_test.db`. Escritura: crear cada BD sobre un path temporal `<nombre>.db.tmp` (conexión sqlite3, ejecutar TODO el DDL+INSERTs de §4.2, `commit`, `close`) y recién entonces `os.replace` al nombre final — nunca queda una BD a medio escribir con el nombre final.
- **Guard de namespace (fix C4, ANTES de escribir nada):** si `get_environment("test-demo-dev")` o `...-test` existe Y su `database` NO apunta dentro de `data_dir()/db_compare/demo/` ⇒ el seed ABORTA con `ValueError("el alias 'test-demo-*' está ocupado por un ambiente ajeno al sandbox; renombralo o borralo antes de sembrar")` — jamás pisa configuración del operador.
- Registro (DESPUÉS de que ambos archivos existen — orden del ciclo de vida, §9.2): `upsert_environment(alias="test-demo-dev", engine="sqlite", host="", port=None, database=str(path_dev), username="demo", notes="Ambiente de demostración de Stacky (generado por el plan 183). Borrable con 'Quitar demo'.")` e ídem `test-demo-test`. Validaciones del registry satisfechas con evidencia: host no se valida para sqlite (`dbcompare_registry.py:130`), port `None`→0 (`:134`), `database` y `username` no vacíos (`:135-138`), alias `test-*` habilita sqlite (`:80-89`).
- **Credencial (fix C1, DESPUÉS del registro):** `dbcompare_registry.set_password(alias, "demo")` por cada alias — dummy requerida por `get_credential` (`:216-217`); si keyring no está disponible, `seed` falla ANTES de registrar (chequear `keyring_available()` al inicio) con error accionable: `"keyring no disponible: el sandbox necesita guardar una credencial dummy (mismo requisito que cualquier ambiente)"` (R11).

### 4.2 DDL y filas EXACTOS por lado (sqlite; ejecutar en este orden literal)

`demo_dev.db` (ORIGEN — la referencia):

```sql
CREATE TABLE RPARAM (CLAVE TEXT NOT NULL PRIMARY KEY, VALOR TEXT NOT NULL, SCOPE TEXT NOT NULL DEFAULT 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('CONN_LEGACY', 'Server=db01;Password=demo123;', 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('MAX_REINTENTOS', '5', 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('MONEDA_DEFECTO', 'PEN', 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('TIMEOUT_SESION', '30', 'GLOBAL');
CREATE TABLE RIDIOMA (CODIGO TEXT NOT NULL, IDIOMA TEXT NOT NULL, TEXTO TEXT NOT NULL, MODULO TEXT, PRIMARY KEY (CODIGO, IDIOMA));
INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO, MODULO) VALUES ('MSG_BIENVENIDA', 'EN', 'Welcome', 'COBRANZA');
INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO, MODULO) VALUES ('MSG_BIENVENIDA', 'ES', 'Bienvenido', 'COBRANZA');
CREATE TABLE RTABL (ID INTEGER NOT NULL PRIMARY KEY, DESCRIPCION TEXT NOT NULL, ACTIVO INTEGER DEFAULT 1, MONTO_TOPE NUMERIC(10,2));
INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (1, 'ESTADOS_COBRANZA', 1, 1000.50);
INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (2, 'TIPOS_MONEDA', 1, 99.99);
CREATE INDEX IX_RTABL_DESCRIPCION ON RTABL (DESCRIPCION);
CREATE TABLE RESTILO (ID INTEGER NOT NULL PRIMARY KEY, COLOR TEXT DEFAULT 'AZUL');
INSERT INTO RESTILO (ID, COLOR) VALUES (1, 'AZUL');
CREATE TABLE RCREDENCIAL (ID INTEGER NOT NULL PRIMARY KEY, USUARIO TEXT NOT NULL, PASSWORD TEXT);
INSERT INTO RCREDENCIAL (ID, USUARIO, PASSWORD) VALUES (1, 'svc_batch', 'hunter2-dev');
CREATE TABLE RLOG (FECHA TEXT, MENSAJE TEXT);
INSERT INTO RLOG (FECHA, MENSAJE) VALUES ('2026-01-01', 'arranque');
CREATE TABLE RSOLO_DEV (ID INTEGER NOT NULL PRIMARY KEY, NOMBRE TEXT);
CREATE VIEW VRESUMEN AS SELECT CLAVE, VALOR FROM RPARAM;
```

`demo_test.db` (DESTINO — el que "driftea"):

```sql
CREATE TABLE RPARAM (CLAVE TEXT NOT NULL PRIMARY KEY, VALOR TEXT NOT NULL, SCOPE TEXT NOT NULL DEFAULT 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('CONN_LEGACY', 'Server=db02;Password=demo456;', 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('MONEDA_DEFECTO', 'USD', 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('PARAM_HUERFANO', '1', 'GLOBAL');
INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('TIMEOUT_SESION', '30', 'GLOBAL');
CREATE TABLE RIDIOMA (CODIGO TEXT NOT NULL, IDIOMA TEXT NOT NULL, TEXTO TEXT NOT NULL, PRIMARY KEY (CODIGO, IDIOMA));
INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO) VALUES ('MSG_BIENVENIDA', 'EN', 'Welcome');
INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO) VALUES ('MSG_BIENVENIDA', 'ES', 'Bienvenido');
CREATE TABLE RTABL (ID INTEGER NOT NULL PRIMARY KEY, DESCRIPCION TEXT, ACTIVO INTEGER DEFAULT 0, MONTO_TOPE NUMERIC(10,2));
INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (1, 'ESTADOS_COBRANZA', 1, 1000.50);
INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (2, 'TIPOS_MONEDA', 1, 99.99);
CREATE TABLE RESTILO (ID INTEGER NOT NULL PRIMARY KEY, COLOR TEXT DEFAULT 'ROJO');
INSERT INTO RESTILO (ID, COLOR) VALUES (1, 'AZUL');
CREATE TABLE RCREDENCIAL (ID INTEGER NOT NULL PRIMARY KEY, USUARIO TEXT NOT NULL, PASSWORD TEXT);
INSERT INTO RCREDENCIAL (ID, USUARIO, PASSWORD) VALUES (1, 'svc_batch', 'hunter2-test');
CREATE TABLE RLOG (FECHA TEXT, MENSAJE TEXT);
INSERT INTO RLOG (FECHA, MENSAJE) VALUES ('2026-01-01', 'arranque');
CREATE TABLE RSOLO_TEST (ID INTEGER NOT NULL PRIMARY KEY, NOMBRE TEXT);
CREATE VIEW VRESUMEN AS SELECT CLAVE, VALOR, SCOPE FROM RPARAM;
```

Los nombres son del dominio RS real, citables: `RIDIOMA` (literales traducibles), `RTABL` (maestra de tablas paramétricas) y `RPARAM` (parámetros clave+valor+scope) están definidos en `services/glossary.py:22-35`; `RESTILO`, `RCREDENCIAL`, `RLOG`, `RSOLO_*` y `VRESUMEN` siguen la convención de prefijo R/V. Determinismo: cero timestamps, cero aleatoriedad — solo estas sentencias, en este orden. (`RESTILO` es nueva en v2 — fix C2: su ÚNICA diferencia es el DEFAULT, para producir el item de severidad `info` que el KPI-5 exige.)

### 4.3 Qué demuestra cada pieza de drift (kinds/severidades ESPERADOS según el código real del diff)

Con `diff_snapshots(source=snapshot(test-demo-dev), target=snapshot(test-demo-test))`:

| Pieza de drift (física) | Kind resultante | Severidad del CHANGE | Severidad del ITEM | Evidencia del criterio |
|---|---|---|---|---|
| `RSOLO_DEV` existe solo en origen | item `table` action `added` (kind efectivo `table_added`) | — | warn | `_walk_object_type`: nombre ausente en target ⇒ "added" (`dbcompare_diff.py:251-252`); severidad de item sin changes = `classify(f"{tipo}_{action}")` (`:231-236`) |
| `RSOLO_TEST` existe solo en destino | item `table` action `removed` (`table_removed`) | — | danger | `:253-254` |
| `RIDIOMA.MODULO` existe solo en origen | `column_removed` | danger | danger | `_diff_columns`: `tc is None` ⇒ removed (`:119-120`) — dirección del CÓDIGO actual (gotcha added/removed conocido y asserted-against-reality) |
| `RTABL.DESCRIPCION` NOT NULL en origen, NULL en destino | `column_nullable_tightened` | danger | (RTABL agrupa) danger | `:127-128` (s_null False, t_null True) |
| `RTABL.ACTIVO` DEFAULT 1 vs DEFAULT 0 | `column_default_changed` | info | (dentro de RTABL: el MAX manda) | `:129-130` |
| `IX_RTABL_DESCRIPCION` existe solo en origen | `index_added` | warn | (dentro de RTABL) | `_diff_by_signature`: firma en source ausente en target ⇒ added_kind (`:144-156`, verificado — sin inversión acá) |
| **`RESTILO.COLOR` DEFAULT 'AZUL' vs 'ROJO' (v2, fix C2)** | `column_default_changed` — ÚNICO change del item | info | **info** (max de un solo change info) | `:129-130` + `_item` max (`:225-236`) — LA pieza que garantiza el item `info` del KPI-5 |
| `VRESUMEN` definición distinta | `view_definition_changed` | warn | warn | `:209-222` (sha distinto) |
| `RPARAM` filas: falta `MAX_REINTENTOS`, difieren `MONEDA_DEFECTO` y `CONN_LEGACY`, sobra `PARAM_HUERFANO` | data-diff: 1 insert + 2 update + 1 delete | — | — | `diff_table_data` (`dbcompare_data.py:168-188`) |
| `RCREDENCIAL.PASSWORD` difiere | data-diff: 1 update (masking 181 por NOMBRE) | — | — | ídem |
| `RLOG` sin PK | candidata NO comparable (reason) — caso claves naturales del 176 | — | — | `dbcompare_data.py:117-118` |

Con `RESTILO`, las severidades de ITEMS del diff = `{info, warn, danger}` (KPI-5 alcanzable). Nota para el implementador: la dirección "added/removed" de COLUMNAS está invertida respecto del docstring del módulo (gotcha CONOCIDO y reportado en el repo); esta tabla lista los kinds RESULTANTES del código ACTUAL — el test del KPI-5 asserta contra esto, no contra una semántica idealizada.

---

## 5. Fases

Orden estricto: F0 → F1 → F2 → F3 → F4 → F5 → F6. TDD en cada una (tests primero, verlos fallar por la razón correcta, implementar, verlos pasar).

---

### F0 — Flag, config y arista

**Objetivo:** registrar `STACKY_DB_COMPARE_DEMO_ENABLED` (default ON) sin comportamiento nuevo.
**Archivos:** los 4 de registro del patrón (§3) + regenerar `harness_defaults.env` por script. FlagSpec: `label="Comparador BD: sandbox de demostración"`, `description="Par de ambientes sqlite de ejemplo (test-demo-dev/test-demo-test, prefijo reservado al sandbox) con drift RS-like, sembrado y quitado con un click. Nada corre solo; jamás toca una BD real. OFF = endpoints 403 y cero UI (los ambientes ya sembrados persisten como ambientes normales)."`.
**Tests PRIMERO — `tests/test_plan183_demo_api.py` (bloque flags):** `test_flag_registrada_bool_on_requires_master`, `test_flag_en_categoria`, `test_config_attr_existe_bool` (patrón determinista de la serie: `isinstance`; el valor efectivo del gate se prueba en F3 con monkeypatch).
**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan183_demo_api.py -q` (+ `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`).
**Criterio (binario):** 3 nuevos + 2 preexistentes verdes. **Flag:** la propia. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F1 — Seed determinista + status

**Objetivo:** `services/dbcompare_demo.py` con `seed_demo_environments()` y `demo_status()`.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_demo.py`:

```python
"""Plan 183 — Sandbox de demostración del comparador (par sqlite RS-like).

Usa el carril sqlite `test-*` YA existente (dbcompare_registry.py:80-89, cuyo
mensaje dice literal "(reservado a tests/demo)") — CERO cambios al motor.
Seed y delete son SIEMPRE por click del operador (HITL). El DDL/filas viven
en este módulo como código (nada empaquetado — apto PyInstaller).

Credencial (fix C1 v2): open_engine exige get_credential != None
(dbcompare_engine.py:88-94; dbcompare_registry.py:210,216-217) — el seed
guarda una password dummy "demo" en keyring (jamás usada en la URL sqlite,
dbcompare_engine.py:74), igual que el fixture del 122
(tests/test_plan122_dbcompare_snapshot.py:66)."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from runtime_paths import data_dir
from services import dbcompare_registry

DEMO_ALIAS_PREFIX = "test-demo-"
DEMO_DEV_ALIAS = "test-demo-dev"
DEMO_TEST_ALIAS = "test-demo-test"
DEMO_DUMMY_PASSWORD = "demo"
_DEMO_DIRNAME = "db_compare/demo"

_DEV_STATEMENTS: tuple[str, ...] = (  # §4.2 lado ORIGEN, orden literal
    ...,
)
_TEST_STATEMENTS: tuple[str, ...] = (  # §4.2 lado DESTINO, orden literal
    ...,
)
# (el implementador pega las sentencias EXACTAS de §4.2; una por string, sin f-strings)


def _demo_dir() -> Path:
    d = data_dir() / _DEMO_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_demo_db(path: Path, statements: tuple[str, ...]) -> None:
    tmp = path.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    os.replace(str(tmp), str(path))


def _alias_is_foreign(alias: str, demo_root: Path) -> bool:
    """Fix C4: True si el alias existe y su database apunta FUERA del sandbox."""
    env = dbcompare_registry.get_environment(alias)
    if env is None:
        return False
    try:
        return not Path(str(env.get("database") or "")).resolve().is_relative_to(demo_root.resolve())
    except (OSError, ValueError):
        return True


def seed_demo_environments() -> dict:
    """Idempotente: SIEMPRE recrea desde cero (archivos por tmp+os.replace,
    registro por upsert, password dummy por set_password). Orden: guards →
    archivos → registro → password (§9.2). Una interrupción deja estados
    detectables por demo_status() y el próximo seed repara."""
    if not dbcompare_registry.keyring_available():
        raise RuntimeError(
            "keyring no disponible: el sandbox necesita guardar una credencial "
            "dummy (mismo requisito que cualquier ambiente)."
        )
    demo_root = _demo_dir()
    for alias in (DEMO_DEV_ALIAS, DEMO_TEST_ALIAS):
        if _alias_is_foreign(alias, demo_root):
            raise ValueError(
                f"el alias '{alias}' está ocupado por un ambiente ajeno al sandbox; "
                "renombralo o borralo antes de sembrar."
            )
    dev_path = demo_root / "demo_dev.db"
    test_path = demo_root / "demo_test.db"
    _write_demo_db(dev_path, _DEV_STATEMENTS)
    _write_demo_db(test_path, _TEST_STATEMENTS)
    for alias, path in ((DEMO_DEV_ALIAS, dev_path), (DEMO_TEST_ALIAS, test_path)):
        dbcompare_registry.upsert_environment(
            alias=alias, engine="sqlite", host="", port=None,
            database=str(path), username="demo",
            notes="Ambiente de demostración de Stacky (plan 183). Quitable con 'Quitar demo'.",
        )
        dbcompare_registry.set_password(alias, DEMO_DUMMY_PASSWORD)  # fix C1
    return {"aliases": [DEMO_DEV_ALIAS, DEMO_TEST_ALIAS], "paths": [str(dev_path), str(test_path)]}


def demo_status() -> dict:
    envs = {e["alias"] for e in dbcompare_registry.list_environments()}
    dev_file = (data_dir() / _DEMO_DIRNAME / "demo_dev.db")
    test_file = (data_dir() / _DEMO_DIRNAME / "demo_test.db")
    from services import dbcompare_runs
    demo_runs = [
        r["run_id"] for r in dbcompare_runs.list_runs(200)
        if str(r.get("source_alias", "")).startswith(DEMO_ALIAS_PREFIX)
        or str(r.get("target_alias", "")).startswith(DEMO_ALIAS_PREFIX)
    ]
    return {
        "registered": DEMO_DEV_ALIAS in envs and DEMO_TEST_ALIAS in envs,
        "files_present": dev_file.exists() and test_file.exists(),
        "aliases": [DEMO_DEV_ALIAS, DEMO_TEST_ALIAS],
        "run_count": len(demo_runs),
    }
```

(Si `keyring_available` no existiera con ese nombre exacto en `dbcompare_registry`, usar el símbolo real — el endpoint de password ya lo consulta, `api/db_compare.py:120-127`; verificar con grep al implementar.)

**Tests PRIMERO — `tests/test_plan183_demo_seed.py`** (monkeypatch `data_dir` en `dbcompare_demo`, `dbcompare_registry`, `dbcompare_snapshot`, `dbcompare_runs` hacia el mismo `tmp_path` + fixture `fake_keyring` del patrón del 122):
- `test_seed_crea_archivos_registra_y_guarda_password` (fix C1): ambos `.db` existen, `list_environments()` trae ambos aliases con `engine=="sqlite"` y `database` DENTRO de `demo/`, y `get_credential(alias)` retorna dict con `password == "demo"` (la cadena del motor completa).
- `test_seed_sin_keyring_falla_claro` (fix C1): monkeypatch `keyring_available` → False ⇒ `RuntimeError` con mensaje accionable, sin archivos creados.
- `test_seed_alias_ajeno_aborta` (fix C4): registrar a mano `test-demo-dev` con `database="C:/otro/lado.db"` ⇒ `seed` lanza `ValueError` y NO toca nada (ni archivos ni registro).
- `test_seed_sin_tmp_residual`: no queda `*.db.tmp`.
- `test_reseed_determinista` (KPI-2): seed → `take_snapshot(alias)` por alias (motor real sqlite) → seed de nuevo → `take_snapshot` de nuevo ⇒ `content_hash` idénticos; y `SELECT * FROM RPARAM ORDER BY CLAVE` idéntico entre seeds.
- `test_status_estados`: sin nada ⇒ `registered False, files_present False`; tras seed ⇒ ambos True; borrando 1 archivo a mano ⇒ `files_present False` con `registered True` (estado "roto" detectable — alimenta `demo-broken`, C6).
- `test_drift_fisico_sembrado`: abrir ambos `.db` con sqlite3 y assertar 5 diferencias físicas puntuales (MODULO solo en dev; índice solo en dev; DESCRIPCION NOT NULL solo en dev; `PARAM_HUERFANO` solo en test; DEFAULT de `RESTILO.COLOR` distinto — fix C2).

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan183_demo_seed.py -q`
**Criterio (binario):** 7 tests verdes; `dbcompare_demo.py` no importa nada de red.
**Flag:** sin efecto aún (sin llamadores). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — DELETE con guard doble

**Objetivo:** `delete_demo()` acotado al sandbox (§3.1), tolerante a locks (fix C3).

**Archivo a editar:** `services/dbcompare_demo.py` — agregar:

```python
def delete_demo() -> dict:
    removed_aliases = []
    for env in dbcompare_registry.list_environments():
        alias = str(env.get("alias") or "")
        if alias.startswith(DEMO_ALIAS_PREFIX):          # GUARD 1: prefijo
            if dbcompare_registry.delete_environment(alias):
                removed_aliases.append(alias)
    demo_root = (data_dir() / _DEMO_DIRNAME).resolve()
    files_removed = False
    error = None
    if demo_root.exists():
        # GUARD 2: contención canónica — jamás borrar fuera del sandbox.
        if not demo_root.is_relative_to((data_dir() / "db_compare").resolve()):
            raise RuntimeError(f"guard de contención violado: {demo_root}")
        for p in demo_root.rglob("*"):
            if not p.resolve().is_relative_to(demo_root):
                raise RuntimeError(f"guard de contención violado: {p}")
        try:
            shutil.rmtree(demo_root)
            files_removed = True
        except OSError as exc:  # fix C3: .db lockeado por una corrida activa (Windows)
            error = (
                "no se pudieron borrar los archivos del sandbox (¿corrida activa "
                f"usándolos?); reintentá al terminar. Detalle: {exc}"
            )
    return {"removed_aliases": removed_aliases, "files_removed": files_removed, "error": error}
```

**Tests PRIMERO — `tests/test_plan183_demo_lifecycle.py`:**
- `test_delete_acotado_guard_doble` (KPI-3): seed + registrar un ambiente fake `prod-x` (sqlserver) + crear señuelo `data_dir()/db_compare/decoy.txt` ⇒ `delete_demo()` ⇒ `prod-x` sigue registrado, `decoy.txt` existe, `demo/` no existe, aliases demo desregistrados.
- `test_delete_idempotente`: segundo `delete_demo()` ⇒ `{"removed_aliases": [], "files_removed": False, "error": None}` sin excepción.
- `test_delete_archivos_lockeados_reporta` (fix C3): monkeypatch `shutil.rmtree` → `PermissionError` ⇒ retorno con `files_removed False` y `error` no nulo, aliases YA desregistrados (estado detectable por `status`: `files_present True, registered False`), sin excepción propagada; un `delete_demo()` posterior (sin el monkeypatch) completa.
- `test_delete_no_borra_snapshots_historicos`: sembrar un snapshot fake en `db_compare/snapshots/test-demo-dev/` ⇒ tras delete sigue existiendo (decisión v1 declarada §3.1).
- `test_seed_tras_delete_funciona`: ciclo delete → seed → status `registered True`.
- `test_interrupcion_archivos_sin_registro`: simular seed interrumpido (solo `_write_demo_db` de ambos, sin registrar) ⇒ `status` = `files_present True, registered False`; `seed` completo lo repara.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan183_demo_lifecycle.py -q`
**Criterio (binario):** 6 tests verdes. **Flag:** aún sin gate (F3). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — API: blueprint `db_compare_demo`

**Objetivo:** exponer seed/status/delete con doble gate de flags.

**Archivo a crear:** `api/db_compare_demo.py` (patrón de la serie: mismo `url_prefix="/db-compare"`, nombre distinto; rutas `/demo/*` libres — verificado contra la tabla completa `api/db_compare.py:52-411`):

```python
from flask import Blueprint, jsonify

import config as _config
from services import dbcompare_demo

bp = Blueprint("db_compare_demo", __name__, url_prefix="/db-compare")


def _require_demo_enabled():
    # Idioma api/db_compare.py:27-29 — instancia de flags = config.config.
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_DEMO_ENABLED", False):
        return jsonify({"ok": False, "error": "Sandbox de demostración deshabilitado (STACKY_DB_COMPARE_DEMO_ENABLED)."}), 403
    return None
```

| Método y ruta | Función | Comportamiento |
|---|---|---|
| `POST /demo/seed` | `seed_demo_route` | 200 `{"ok": true, **seed_demo_environments()}`; 409 `{"ok": false, "error": ...}` ante `ValueError` (alias ajeno, fix C4); 503 ante el `RuntimeError` de keyring (fix C1); 500 controlado ante `OSError` |
| `GET /demo/status` | `demo_status_route` | 200 `{"ok": true, "status": demo_status()}` |
| `DELETE /demo` | `delete_demo_route` | resultado de `delete_demo()`: si `error` es null ⇒ 200 `{"ok": true, ...}`; si `error` no es null (archivos lockeados, fix C3) ⇒ 409 `{"ok": false, ...}` con el detalle (la CONFIRMACIÓN es responsabilidad de la UI — F4; la API es idempotente e inocua fuera del sandbox por §3.1) |

**Registro:** `api/__init__.py` — 2 líneas con el idioma de `:57`/`:118`.

**Tests PRIMERO — completar `tests/test_plan183_demo_api.py`:** `test_403_flags_off` (KPI-4: master OFF y demo OFF, en las 3 rutas), `test_seed_status_delete_feliz` (cliente Flask, tmp data_dir + fake keyring), `test_seed_alias_ajeno_409`, `test_delete_lockeado_409` (monkeypatch rmtree), `test_delete_sin_demo_ok_vacio`.
**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan183_demo_api.py -q`
**Criterio (binario):** 5+3 verdes; `api/db_compare.py` sin diff. **Flag:** doble gate. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — Frontend: panel demo (con estado roto) + regla sqlite-sin-contraseña

**Objetivo:** CTA de 1 click, banner de demo activo con "Quitar demo" (confirmación), estado `demo-broken` con "Re-sembrar" ([ADICIÓN ARQUITECTO], fix C6), y el fix del wizard (§3.2).

**Archivos a crear:**
1. `frontend/src/components/dbcompare/demoLogic.ts` — puro:
   - `demoPanelState(environments: {alias: string}[], status: {registered: boolean; files_present: boolean} | null): "cta-empty" | "cta-secondary" | "demo-active" | "demo-broken"` — regla EXACTA: si `status` no es null y `registered !== files_present` ⇒ `"demo-broken"` (fix C6); si ALGÚN alias empieza con `test-demo-` ⇒ `"demo-active"`; si `environments.length === 0` ⇒ `"cta-empty"`; si no ⇒ `"cta-secondary"`.
   - `isDemoAlias(alias: string): boolean`.
2. `frontend/src/components/dbcompare/DemoSandboxPanel.tsx` — autocontenido; props `{ environments: DbEnvironment[]; onChanged: () => void }`:
   - `DbCompareDemo.status()` al montar; si RECHAZA (403/red) ⇒ `return null` (KPI-4, patrón health→null).
   - `demoPanelState`: `cta-empty` ⇒ tarjeta prominente "Probar con ambientes de ejemplo" (subtítulo: "Crea un par sqlite local con drift de ejemplo. Sin credenciales, sin red."); `cta-secondary` ⇒ botón discreto con el mismo texto; `demo-active` ⇒ banner "Ambientes de demostración activos (`test-demo-dev` → `test-demo-test`)" + botón "Quitar demo" con `window.confirm("¿Quitar los ambientes de demostración? Se borran solo los archivos del sandbox.")` antes de `DbCompareDemo.remove()`; **`demo-broken` ⇒ banner de advertencia "El sandbox de demostración quedó a medias (archivos y registro desincronizados)" + botón "Re-sembrar" que llama `DbCompareDemo.seed()`** ([ADICIÓN ARQUITECTO] — reparación en 1 click; el seed ya es reparador por diseño).
   - Si `remove()` responde `ok:false` (409 archivos lockeados, fix C3) ⇒ mostrar el `error` del payload en el banner (sin crash).
   - Tras seed/remove exitoso ⇒ `onChanged()`.
   - CERO `style={{...}}`; clases nuevas al final de `dbcompare.module.css` (`.demoCta`, `.demoBanner`, `.demoSecondary`, `.demoBroken`) con tokens `--dbc-*`/tema existentes.
3. `frontend/src/components/dbcompare/__tests__/demoLogic.test.ts` — vitest: los 4 estados (incluye `demo-broken` en ambas direcciones: registered sin files y files sin registered) + `isDemoAlias`.
4. `frontend/src/components/dbcompare/__tests__/wizardLogicDemo.test.ts` — vitest (KPI-7): sqlite sin password ⇒ target `enabled` y `canLaunch.ok` true; sqlserver sin password ⇒ sigue deshabilitado (las dos direcciones).

**Archivos a editar (mínimos):**
5. `wizardLogic.ts` + `CompareWizard.tsx` — los 5 microhunks EXACTOS de §3.2 (líneas verificadas).
6. `endpoints.ts` — append AL FINAL REAL del archivo (hoy el último export es `Incidents`, `:4155`; verificar con `tail -n 3` / `Get-Content -Tail 3`; gotcha de merge de la serie):
   ```typescript
   // Plan 183 — Sandbox de demostración del comparador.
   export const DbCompareDemo = {
     seed: () => api.post<{ ok: boolean; aliases: string[]; paths: string[] }>("/api/db-compare/demo/seed", {}),
     status: () => api.get<{ ok: boolean; status: { registered: boolean; files_present: boolean; aliases: string[]; run_count: number } }>("/api/db-compare/demo/status"),
     remove: () => api.delete<{ ok: boolean; removed_aliases: string[]; files_removed: boolean; error: string | null }>("/api/db-compare/demo"),
   };
   ```
   (`api.delete` EXISTE — verificado en la serie: `DbCompare.deleteEnvironment`, `endpoints.ts:3989-3992`.)
7. `DbComparePage.tsx` — EXACTAMENTE 2 ediciones: 1 import + 1 JSX `<DemoSandboxPanel environments={environments} onChanged={() => { reloadEnvironments(); reloadRuns(); }} />` inmediatamente DESPUÉS del bloque `missingDrivers` (`:129-139`) y ANTES de `<DbCompareSettingsSection />` (`:141`) — anchor VERIFICADO; los callbacks `reloadEnvironments`/`reloadRuns` ya existen (`:47-56`).

**Comandos:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/demoLogic.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/wizardLogicDemo.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/wizardLogic.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio (binario):** los 3 vitest verdes (incluido el PREEXISTENTE sin editar) + `tsc` limpio + 0 `style={{` en los `.tsx` nuevos + `git diff` de `DbComparePage.tsx` = 2 hunks.
**Flag:** el panel se auto-oculta ante 403 (KPI-4). **Runtimes:** idéntico. **Trabajo del operador:** ninguno (probar la demo es opt-in de 1 click; quitarla, 1 click + confirmación; repararla, 1 click).

---

### F5 — E2E integral y catálogo de severidades

**Objetivo:** demostrar con el MOTOR REAL que el sandbox entrega el ciclo completo y el catálogo prometido.

**Tests PRIMERO — `tests/test_plan183_demo_e2e.py`** (monkeypatch de `data_dir` global a `tmp_path` + fake keyring; motor real sqlite, sin monkeypatch de snapshot/diff/data):
- `test_ciclo_completo_sqlite` (KPI-1): `seed` → `dbcompare_runs.create_run(DEMO_DEV_ALIAS, DEMO_TEST_ALIAS, mode="fresh")` → esperar el thread (poll `get_run` con timeout corto) → `status=="done"`, `summary.parity_score < 100`, `items` no vacío; `data-candidates` del run: `RPARAM` comparable, `RLOG` no comparable con reason de PK.
- `test_catalogo_severidades` (KPI-5, fix C2): del diff del run: `{it["severity"] for it in items} == {"info","warn","danger"}` (el `info` viene del item de `RESTILO`) y los kinds de los changes incluyen `{"column_removed","column_nullable_tightened","column_default_changed","index_added","view_definition_changed"}` y hay items con action `added` y `removed` a nivel tabla (§4.3).
- `test_base_comun_smokes` (KPI-6): `run_data_diff(run_id, [{"schema": "main", "table": "RPARAM"}, {"schema": "main", "table": "RCREDENCIAL"}])` → el run trae data_diff `done` con `RPARAM` = 1 insert + 2 updates + 1 delete y `RCREDENCIAL` = 1 update (los números EXACTOS de §4.3).

(Nota de aislamiento de tests: este archivo usa el motor completo con archivos sqlite reales bajo `tmp_path` — cero red, cero egress; el thread de `create_run` es el del motor y termina solo; mismo patrón que los E2E sqlite del 122/126.)

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan183_demo_e2e.py -q`
**Criterio (binario):** 3 tests verdes. **Flag:** N/A (llama servicios directo). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F6 — Cierre

1. Registro de los 4 tests backend en ambos runners (grep).
2. Correr POR ARCHIVO: los 4 nuevos + `tests/test_harness_flags.py` + `tests/test_harness_flags_requires.py` + `tests/test_plan122_dbcompare_registry.py` + `tests/test_plan122_dbcompare_api.py` + `tests/test_plan122_dbcompare_snapshot.py` + `tests/test_plan123_dbcompare_runs.py` + `tests/test_plan126_dbcompare_data_diff.py` (perímetro del registry/motor compartido).
3. `"./venv/Scripts/python.exe" -m compileall services/dbcompare_demo.py api/db_compare_demo.py` limpio.
4. Frontend: los 3 vitest de F4 + `tsc`.
5. Smoke manual documentado en el PR: instalación limpia → Comparador → "Probar con ambientes de ejemplo" → comparar → explorar diff/treemap/drill-down (verificar el item `info` de RESTILO en el mapa) → data-diff RPARAM → generar scripts → apagar la flag por UI → el panel desaparece PERO los ambientes siguen en el wizard (decisión C5 declarada) → re-encender → "Quitar demo" (con confirmación) → todo desaparece del wizard; verificar en disco que `demo/` no existe y `environments.json` no tiene aliases demo.

**Criterio (binario):** puntos 1-4 verdes; punto 5 documentado. **Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | DELETE toca algo fuera del sandbox | Pérdida de datos del operador | Guard doble §3.1 (prefijo de alias + contención canónica con `is_relative_to` y abort) + confirmación en UI + KPI-3 negativo con señuelos |
| R2 | El wizard no deja seleccionar los ambientes demo (gate de password) | Demo inservible | Hallazgo detectado y resuelto con 5 microhunks (líneas verificadas §3.2); además los demo llevan password dummy (C1) así que pasan el gate por partida doble; KPI-7 con test preexistente verde |
| R3 | Re-seed no determinista a nivel bytes del `.db` | KPI imposible | Redefinido HONESTAMENTE (KPI-2): el determinismo prometido es el observable por el motor (`content_hash` del snapshot + SELECTs), no los bytes del archivo — límite declarado |
| R4 | Seed interrumpido deja estado a medias | Confusión | Orden guards→archivos→registro→password + escritura tmp+`os.replace` + `status` que distingue `files_present`/`registered` + estado `demo-broken` con "Re-sembrar" (C6) + re-seed reparador (tests F1/F2; §9.2) |
| R5 | Los runs/snapshots demo "ensucian" el historial real | Ruido y consumo de retención | Alias autoexplicativo en la timeline (`RunsTimeline.tsx:30`); **los runs demo CONSUMEN slots de la retención compartida (`_MAX_RUNS_KEPT=100`) y pueden acortar el histórico real (fix C9)** — mitigado por "Quitar demo" temprano y la retención normal; `status.run_count` los reporta; decisión v1 §3.1 de no borrarlos declarada |
| R6 | Coexistencia con el radar del 178 (en papel): el par demo aparecería en la matriz | Sorpresa visual | Nota de coherencia: es CORRECTO que aparezca (son ambientes registrados reales para el motor); el prefijo `test-demo-` lo hace evidente; si molesta, "Quitar demo" lo saca de todos lados |
| R7 | PyInstaller: recursos del seed perdidos en el freeze | Demo rota en deploy | TODO por código (`sqlite3` stdlib + strings en el módulo); cero data-files; `compileall` en F6 contra el gotcha de submódulos |
| R8 | Sesión paralela ocupa el número 183 | Colisión de numeración (precedente 171) | Número recalculado listando `docs/` inmediatamente antes del Write; renumerar antes de commitear si aparece otro |
| R9 | El E2E de F5 depende del thread real de `create_run` | Flakiness | Poll con timeout corto sobre archivos locales (sin red); mismo patrón ya estable de los E2E sqlite del 122/126; si el runner lo muestra flaky, el fallback documentado es llamar `_execute_run` inline (mismo módulo) — decisión del implementador ANOTADA en el test |
| R10 | `window.confirm` nativo rompe la línea visual (el 164, en papel, define diálogo canónico) | Inconsistencia UX futura | v1 usa `confirm()` (patrón vigente en main); integración con el diálogo canónico del 164 queda CONDICIONAL futura (mismo trato que toda integración con planes en papel) |
| R11 | **(v2, fix C1)** Keyring no disponible en la instalación | Seed imposible | El seed chequea `keyring_available()` PRIMERO y falla con mensaje accionable (503 en API) — MISMO límite que el alta normal de contraseñas (`api/db_compare.py:120-127`); sin keyring, el comparador entero está igual de limitado (ningún ambiente puede guardar password) |
| R12 | **(v2, fix C5)** Flag OFF después de sembrar: los ambientes demo persisten sin panel para quitarlos | Confusión ("no puedo sacar la demo") | Decisión EXPLÍCITA: los ambientes sembrados son ambientes normales del motor (agnóstico a la flag) — persisten y funcionan; para quitarlos: re-encender la flag y "Quitar demo", o la baja normal de ambientes (`DELETE /environments/<alias>`, `api/db_compare.py:101-108`); declarado en la description de la flag y §9.2 |
| R13 | **(v2, fix C4)** El operador ya usaba un alias `test-demo-*` propio | El seed pisaría su config | Guard de namespace: el seed ABORTA con error claro si el alias apunta fuera de `demo/` (test `test_seed_alias_ajeno_aborta`); prefijo declarado RESERVADO |

---

## 7. Fuera de scope

- **Sembrar en motores reales (sqlserver/oracle)**: NUNCA — el sandbox es sqlite local por definición; Stacky jamás escribe en BDs del cliente.
- **Datasets demo grandes o configurables**: fuera de v1; el valor es el catálogo de kinds, no el volumen.
- **Borrado de snapshots/runs/bundles históricos del par demo en el DELETE**: decisión v1 explícita (§3.1) — mínima superficie destructiva; un plan futuro puede agregar "limpieza profunda" con su propio guard.
- **Tour guiado/onboarding interactivo sobre el demo**: fuera; el 151 (onboarding first-run) es el lugar natural si algún día se conectan.
- **Auto-seed en primera instalación (sin click)**: NO — violaría "nada corre solo"; el CTA de 1 click es el máximo de proactividad permitido.
- **Eximir a sqlite de la credencial en `open_engine`** (3 líneas en el motor que harían innecesaria la password dummy): DESCARTADO deliberadamente — violaría "CERO cambios al motor" y el precedente del repo es el contrario (el fixture del 122 guarda password dummy, `tests/test_plan122_dbcompare_snapshot.py:66`); la v1 de este plan descartaba la password dummy citando la línea equivocada (`dbcompare_engine.py:141` es de `test_connection`) — corregido en v2 (fix C1) con la cadena real (`get_credential:216-217` → `open_engine:88-94`).

---

## 8. Glosario, orden de implementación y DoD global

### Glosario

- **Sandbox demo**: el par `test-demo-dev`/`test-demo-test` + sus archivos bajo `data_dir()/db_compare/demo/` + su password dummy en keyring.
- **Seed**: creación idempotente con guards (namespace + keyring) → archivos (tmp+replace) → registro (upsert) → password dummy — §4.1.
- **Guard doble**: prefijo de alias + contención canónica de paths (§3.1).
- **Namespace reservado**: el prefijo `test-demo-` pertenece al sandbox; el seed jamás adopta un alias ajeno (fix C4).
- **Carril `test-*`**: la regla YA existente del registry que habilita sqlite solo para esos aliases (`dbcompare_registry.py:80-89`).
- **Drift sembrado**: las diferencias FÍSICAS exactas de §4.2, cada una mapeada a su kind/severidad esperado (§4.3), incluido el item `info` de `RESTILO`.
- **`demo-broken`**: estado del panel cuando registro y archivos están desincronizados — CTA "Re-sembrar" (fix C6).
- **CTA**: el botón "Probar con ambientes de ejemplo" (estado según `demoPanelState`).

### Orden de implementación (estricto)

F0 (flag) → F1 (seed+status) → F2 (delete+guard) → F3 (API) → F4 (frontend+wizard fix) → F5 (E2E) → F6 (cierre). F5 depende de F1 solamente, pero se implementa al final para validar el conjunto.

### Definition of Done global

1. Los 7 KPIs de §1.2 verificados con sus tests/comandos.
2. Los 4 `tests/test_plan183_*.py` verdes POR ARCHIVO y registrados en ambos runners.
3. Los 7 preexistentes de F6 punto 2 + `__tests__/wizardLogic.test.ts` verdes SIN editar ninguno.
4. Frontend: vitest nuevos verdes, `tsc --noEmit` limpio, 0 `style={{` en `.tsx` nuevos.
5. `harness_defaults.env` regenerado por script (flag nueva en `true`).
6. `git diff --stat` solo lista los archivos de la fila "183" de §2bis — en particular NO lista `dbcompare_registry.py`, `dbcompare_engine.py`, `dbcompare_snapshot.py`, `dbcompare_diff.py`, `dbcompare_data.py`, `dbcompare_runs.py`, `dbcompare_scripts.py` ni `api/db_compare.py`.
7. Smoke manual de F6 documentado en el PR (incluye la verificación de R12: flag OFF ⇒ ambientes persisten).

---

## 9. PERÍMETRO enumerado

### 9.1 Superficies

| Superficie | Evidencia | Impacto del 183 | Sello |
|---|---|---|---|
| Registro de ambientes (alta/baja/lista) | `dbcompare_registry.py:114-164,167-175,102-104`; persiste en `db_compare/environments.json` (`:27,37-38`); upsert PISA sin guard (`:159-160`) | REUSADO vía API pública; guard de namespace en el SEED (C4); módulo SIN diff | tests F1/F2 + DoD-6 |
| Carril sqlite `test-*` | `:80-89` (mensaje "(reservado a tests/demo)" `:84-86`) | habilita los aliases demo sin tocar nada | cita + `test_seed_crea_archivos_registra_y_guarda_password` |
| **Credencial / keyring (v2, fix C1 — la fila que faltaba)** | `get_credential` exige keyring + password (`dbcompare_registry.py:203-218`, None en `:210,:216-217`); `open_engine` lanza ante None (`dbcompare_engine.py:88-94`); URL sqlite sin password (`:74`); precedente fixture 122 (`test_plan122_dbcompare_snapshot.py:66`) | el seed guarda password dummy `"demo"` y el delete la limpia (`:175`); sin keyring ⇒ error claro (R11) | `test_seed_crea_..._y_guarda_password` + `test_seed_sin_keyring_falla_claro` + E2E |
| Engine/conexión sqlite | `dbcompare_engine.py:73-74` (URL por `database`=path), `:96` (sin driver) | consumido tal cual | E2E F5 |
| Snapshot/diff/runs/data/scripts | módulos intactos | generan sobre el par demo como con cualquier ambiente | E2E F5 + KPI-5 |
| Endpoint de alta real | `api/db_compare.py:78-98` | NO se toca (el seed llama al servicio, misma vía de persistencia) | DoD-6 |
| Rutas nuevas `/demo/*` | tabla de rutas existentes `api/db_compare.py:52-411` sin `/demo` | blueprint nuevo, cero colisión | `test_403_flags_off` + registro `api/__init__.py:57,118` |
| Wizard (selección de par) | gate de password en `CompareWizard.tsx:39,85-86,95` y `wizardLogic.ts:39-41,61-66` (líneas VERIFICADAS) | 5 microhunks §3.2 | KPI-7 + preexistente `__tests__/wizardLogic.test.ts` verde |
| Historial (timeline) | `RunsTimeline.tsx:30` muestra `source → target` | sin cambios; alias autoexplicativo | cita (decisión §3) |
| Data-candidates / picker | `DataParitySection.tsx:121-145` muestra no-comparables con reason | `RLOG` aparece con su reason sin cambios | E2E F5 (KPI-1) |
| Panel del arnés (flags) | categoría `comparador_bd` | 1 flag nueva visible/toggleable | tests F0 |
| Deploy congelado | gotcha PyInstaller | todo por código, stdlib | R7 + compileall F6 |
| Punto de montaje `DbComparePage.tsx` | `:129-139` missingDrivers, `:141` Settings (VERIFICADO) | 1 import + 1 JSX; anchors acumulados de la serie en §2bis (C7) | `git diff` 2 hunks |

### 9.2 Comportamientos (un verbo prometido = una fila con garantía)

| Verbo | Primera vez | Repetición | Interrupción a mitad | Limpieza | Coexistencia |
|---|---|---|---|---|---|
| **Sembrar** | guards (namespace C4 + keyring C1) → archivos tmp+`os.replace` → registro → password dummy (§4.1) | idempotente: re-crea desde cero; `upsert` actualiza sin duplicar (`:159-162`); determinismo KPI-2 | muere entre pasos ⇒ estados detectables por `status` (`files_present`/`registered` desincronizados ⇒ `demo-broken` con "Re-sembrar", C6); el próximo seed pisa TODO | — | convive con ambientes reales; JAMÁS adopta un alias ajeno (C4) |
| **Conectar/abrir engine (v2 — el verbo que faltaba, C1)** | `open_engine(alias)` exige credencial en keyring — el seed la dejó (`"demo"`); URL sqlite sin password | cada snapshot/run reusa la misma cadena | keyring caído después del seed ⇒ `open_engine` falla con el mensaje del motor (mismo que cualquier ambiente) — sin manejo especial | el delete limpia la password (`:175`) | la password dummy convive en el keyring con las reales bajo el mismo service key (aliases distintos) |
| **Re-sembrar** | = sembrar (misma función, sin ramas) | `test_reseed_determinista` (KPI-2) | ídem sembrar | — | los snapshots previos del alias siguen; `latest_snapshot` reflejará el nuevo estado tras el próximo snapshot |
| **Limpiar (delete)** | guard doble §3.1; borra `demo/` entera y desregistra SOLO `test-demo-*` (+password) | idempotente (`test_delete_idempotente`) | archivos lockeados por corrida activa ⇒ NO 500: retorno con `error` y API 409 (C3); re-ejecutable; si muere tras desregistrar ⇒ `status`/`demo-broken` lo muestra | NO borra snapshots/runs históricos (decisión v1 §3.1) | señuelos y ambientes reales intactos (KPI-3); el run activo del par termina en `error` inofensivo |
| **Apagar la flag (v2 — C5)** | endpoints 403 + panel oculto | — | — | los ambientes/archivos sembrados PERSISTEN (el motor es agnóstico a la flag) — decisión explícita | quitables re-encendiendo la flag, o por la baja normal (`DELETE /environments/<alias>`, `api/db_compare.py:101-108`); declarado en la flag description (R12) |
| **Aislar** | sqlite local, cero red (carril `test-*`) | — | — | — | credencial = dummy `"demo"` (requisito de contrato, no secreto); `username="demo"` ídem (`:137-138`) |
| **Correr smokes** | base común probada (KPI-6) | los smokes son re-ejecutables (el par persiste hasta "Quitar demo") | — | — | mapa §2ter por plan |
| **Seleccionar en el wizard** | regla sqlite-sin-password (§3.2) + password dummy presente (C1) | — | — | — | sqlserver/oracle conservan el gate EXACTO (KPI-7 en ambas direcciones) |

---

**Changelog interno:** v1 (2026-07-18) — propuesta inicial. v2 (2026-07-18) — crítica del juez: C1 bloqueante (cadena de credencial real `get_credential:216-217`→`open_engine:88-94`; password dummy obligatoria con el precedente del fixture 122; la cita `:141` de la v1 era de `test_connection`) + C2 bloqueante (KPI-5 imposible sin un item `info` — tabla `RESTILO` nueva) + C3 delete con locks + C4 namespace reservado + C5 verbo "Apagar" + C6 estado `demo-broken` + C7 anchors acumulados + C8 coherencia 157 + C9 retención explícita.
Auto-consistencia KPI↔spec (re-verificada v2): KPI-1↔el E2E usa `create_run` real y el seed deja la CADENA COMPLETA (archivos+registro+password) que `open_engine` exige; KPI-2↔determinismo observable (content_hash + SELECTs), bytes NO prometidos; KPI-3↔guards literales de §3.1 con señuelos; KPI-4↔gate en las 3 rutas + panel null; KPI-5↔severidades de ITEMS simuladas contra `_item` (`:225-236`): `RESTILO` garantiza el `info`, y los kinds de changes se assertan contra la tabla §4.3 derivada del código actual (gotcha de dirección incluido); KPI-6↔counts 1+2+1 y 1 derivados fila por fila de §4.2; KPI-7↔5 microhunks con líneas verificadas y test preexistente sin editar; R4/C6↔cada celda de "Sembrar"/"Limpiar" de §9.2 tiene su test nombrado.
