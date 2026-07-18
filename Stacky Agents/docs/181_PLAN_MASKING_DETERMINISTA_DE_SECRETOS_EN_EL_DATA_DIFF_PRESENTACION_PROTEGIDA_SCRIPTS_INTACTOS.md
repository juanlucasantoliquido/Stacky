# Plan 181 — Masking determinista de secretos/PII en el data-diff: presentación protegida por default, scripts intactos, overrides HITL por columna

**Estado:** CRITICADO (v2, 2026-07-18, juez `criticar-y-mejorar-plan`). La v1 (PROPUESTO 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`) fue **RECHAZADA** por un bloqueante (C1: el "punto único de serialización" era falso — `GET /runs` sirve el `data_diff` CRUDO completo de cada run listado, porque `list_runs` excluye solo la clave `"diff"` (`dbcompare_runs.py:227`) y el data-diff se persiste como clave top-level del run; con masking ON, la lista que el frontend carga en cada reload seguía llevando todos los secretos al browser). Esta v2 lo corrige in place y queda lista para `implementar-plan-stacky`.

**Serie:** Comparador de BD — capa 6 (seguridad de presentación del data-diff). Prerequisito declarado del futuro "vigía de DATOS" (el 178 §7 lo excluyó por PII: "si algún día se considera, requiere su propio plan con masking" — este plan ES ese masking). Relación con 157/176/178/179/180: §2bis, con los solapes compartidos declarados con guía de merge.

## Versión: v1 -> v2 (2026-07-18, criticar-y-mejorar-plan)

**CHANGELOG v1 -> v2:**
- **C1 (BLOQUEANTE, resuelto):** F3 v1 afirmaba "el data-diff solo viaja por `get_run_route`; `list_runs` excluye `diff`" — VERDAD A MEDIAS refutable con la línea que el propio plan citaba: `dbcompare_runs.py:227` excluye SOLO `"diff"`, y `run_data_diff` escribe `data_diff` como clave top-level del run (`dbcompare_data.py:215` "escritura en el archivo del run") ⇒ `GET /runs` (que el frontend llama con `listRuns(20)` en cada reload) servía TODAS las filas crudas — passwords incluidos — con masking ON. KPI-1 ("toda superficie de presentación") violado por diseño. Fix: excluir `data_diff` de la metadata de `list_runs` (1 línea: `if k not in ("diff", "data_diff")` — además elimina un problema de peso de payload preexistente: la lista arrastraba hasta 20 tablas × 5000 filas × 2 lados por run); KPI-8 nuevo lo sella; §2bis gana la fila `dbcompare_runs.py` (1 línea, zona distinta del kwarg del 178 y del modo histórico del 176) con guía de merge; tests nuevos de perímetro (`test_list_runs_sin_data_diff`, `test_post_data_diff_no_sirve_filas`).
- **C2 (IMPORTANTE, resuelto) [ADICIÓN ARQUITECTO]:** el plan no enumeraba las superficies donde el operador VE valores del data-diff — el visor de scripts del bundle (`GET /runs/<id>/scripts/file` + zip) muestra los `.sql` con valores REALES por doctrina, y un operador que ve `••••` en el grid podía creer que "está protegido" en todos lados. Fix: **tabla de superficies** (cubiertas / no cubiertas POR DOCTRINA / fuera de HTTP) como contrato en §3.1, cada una con test o declaración explícita; y la barra de masking de la UI incluye la leyenda literal "Los scripts del bundle contienen valores reales".
- **C3 (IMPORTANTE, resuelto):** la "regla de 2 intentos" de lookup de prefs (literal + upper) era asimétrica y rota: una pref guardada con case mixto (`dbo.RUSUARIOS.Password`) jamás matchea el lookup upper (busca la CLAVE upper en un dict con claves mixtas) — el ida-vuelta SQL Server (mixto) / Oracle (upper) fallaba. Fix: **clave canónica UPPERCASE en ambos lados** — `set_override` guarda `key.upper()` y `masking_plan` busca SOLO `key.upper()`; contrato §4 actualizado; test de case cruzado.
- **C4 (IMPORTANTE, resuelto):** `mask_value` con "últimos 2 chars" sobre un secreto de 5-7 chars revelaba hasta ~1/3 del secreto. Fix: el sufijo de 2 chars aparece SOLO si `len(str(value)) >= 8`; si no, placeholder pelado. Golden test ajustado (`"secret"` (6) → `"••••"`).
- **C5 (IMPORTANTE, resuelto):** el test del KPI-4 no fijaba el ORDEN de operaciones que detectaría una mutación accidental compartida: ahora el test hace `GET /runs/<id>` (masking ON, respuesta enmascarada verificada) y RECIÉN DESPUÉS genera el bundle, comparando byte a byte contra el bundle con OFF — si `apply_masking` mutara el dict por error, este orden lo detecta (aunque la cadena real re-lee de disco: `get_run` → `_read_run` fresco por request y `generate_parity_bundle(run_id)` re-lee por id — verificado).
- **C6 (MENOR, resuelto):** trade-off de enmascarar `changed[].pk` declarado (R9 nuevo): la identidad visual de la fila se degrada; mitigación: sufijo de 2 chars si len≥8 (distinguibilidad parcial) + revelar de 1 click; enmascarar la PK sigue siendo lo correcto (una PK sensible es un secreto igual).
- **C7 (MENOR, resuelto):** overrides huérfanos (columna que ya no aparece en el diff) declarados: se ignoran inofensivamente y NO se limpian (la columna puede volver en el próximo run) — regla explícita en §4.
- **C8 (MENOR, resuelto):** F5 v1 dejaba el verbo HTTP a decidir "con el archivo a la vista" (si `api.put` no existía, cambiar F4 a POST — decisión tardía que cruzaba fases). Fix: **POST decidido AHORA** para F4 y F5 (`POST /masking/prefs`): `api.post` existe con certeza en `endpoints.ts` (todos los objetos lo usan); cero branch para el implementador.
- **C9 (MENOR, resuelto):** con flag ON y cero columnas masked, `masked_columns: []` está SIEMPRE presente por tabla — ahora declarado como señal estable para la UI (el byte-idéntico es solo para OFF, KPI-2).
- **C10 (MENOR, resuelto):** costo del deepcopy cuantificado en R5: solo tablas con masked, caps 126 (≤20 tablas × ≤5000 filas × 2 lados), y el polling de progreso NO paga costo (sin `data_diff` ⇒ early-return; el data-diff aparece recién con el run `done`).
- **Dictamen del juez sobre la pasada de auto-consistencia v1:** SÓLIDA en sus 7 pares (muestreados 4: KPI-1↔pk contra el shape real `dbcompare_data.py:177-188` ✓; KPI-2↔early-return del mismo objeto ✓; KPI-4↔cadena de disco `get_run`→`_read_run` fresco + `generate_parity_bundle(run_id)` ✓; KPI-5↔tupla+muestreo determinista por PK ordenada `:168-170` ✓) pero INCOMPLETA de perímetro: verificó lo que el autor ya creía y no atacó las superficies vecinas (C1 estaba fuera de los 7 pares). Lección incorporada: la v2 agrega la tabla de superficies con test por superficie.

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Que los VALORES de columnas sensibles (passwords, tokens, connection strings) que el data-diff del 126 trae de las tablas comparadas lleguen ENMASCARADOS por default a toda superficie de presentación (respuestas API del run Y de la lista de runs → grid de la UI), sin tocar jamás el motor ni los scripts DML del bundle — y que revelar una columna sea UNA decisión humana de 1 click, persistida.

### 1.2 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | Con la flag ON, un run cuyo data-diff contiene la columna `PASSWORD` sirve por `GET /api/db-compare/runs/<id>` esa columna enmascarada en TODAS sus apariciones (filas de `only_source`, `only_target`, `changed[].cells` y `changed[].pk`), y la tabla trae el campo aditivo `masked_columns` con `["PASSWORD"]` (con ON el campo está SIEMPRE, `[]` si nada se enmascaró — C9). | `tests/test_plan181_response.py::test_password_enmascarada_en_respuesta` |
| KPI-2 | Con `STACKY_DB_COMPARE_MASKING_ENABLED=false`, la respuesta de `GET /runs/<id>` es BYTE-idéntica a main (mismo `json.dumps` del mismo dict, sin copia ni campo aditivo), para el mismo run sembrado con datos sensibles. | `tests/test_plan181_response.py::test_off_byte_identico` |
| KPI-3 | Un override `visible` por columna (POST prefs) hace que el próximo GET del run sirva esa columna en crudo, y el override SOBREVIVE un reinicio: las prefs viven SOLO en disco (`masking_prefs.json`) y se releen en cada aplicación — cero estado en memoria. | `tests/test_plan181_prefs.py::test_override_visible_persiste_y_releen_disco` |
| KPI-4 | **BLOQUEANTE — scripts intactos:** con masking ON, PRIMERO se hace `GET /runs/<id>` (respuesta enmascarada verificada) y DESPUÉS se genera el bundle (`POST /runs/<id>/scripts`): los archivos DML son BYTE-idénticos a los generados con masking OFF y llevan los valores REALES (el orden GET→bundle detecta cualquier mutación accidental — C5). | `tests/test_plan181_response.py::test_bundle_dml_byte_identico_con_masking_on` |
| KPI-5 | Detectores golden: por NOMBRE, `PASSWORD`, `Contrasena`, `API_KEY`, `CADENA_CONEXION`, `ClaveSecreta` ⇒ masked y `CLAVE`, `DESCRIPCION`, `EMAIL`, `VALOR` ⇒ visible; por VALOR (solo si el nombre no decidió), `eyJhbGciOiJIUzI1NiJ9.x` ⇒ masked, `Server=x;Password=y;` ⇒ masked, `hola` y `12345678` ⇒ visible. | `tests/test_plan181_masking_core.py` |
| KPI-6 | `apply_masking` NO muta su entrada: tras aplicarlo, el dict original del run/data-diff es estructuralmente idéntico a su copia previa. | `tests/test_plan181_masking_core.py::test_apply_no_muta_original` |
| KPI-7 | La suite dbcompare preexistente afectable (`test_plan122_dbcompare_api.py`, `test_plan123_dbcompare_api.py`, `test_plan123_dbcompare_runs.py`, `test_plan126_dbcompare_data_api.py`, `test_plan126_dbcompare_data_diff.py`, `test_plan126_dbcompare_data_scripts.py`) queda verde POR ARCHIVO sin editar ninguno. Si alguno fijara que `list_runs` incluye `data_diff` (improbable), es HALLAZGO a reportar — se corrige el diseño, JAMÁS el test (patrón de la serie). | comandos de F6 |
| KPI-8 | **(nuevo v2, fix C1)** `GET /runs` (lista) NUNCA sirve `data_diff` — ni crudo ni enmascarado: la metadata de cada run en la lista excluye `diff` Y `data_diff`; y `POST /runs/<id>/data-diff` responde el ack de arranque sin filas. | `tests/test_plan181_response.py::test_list_runs_sin_data_diff` + `::test_post_data_diff_no_sirve_filas` |

---

## 2. Por qué ahora / gap

1. **El diferido está anotado TRES veces en la serie**: 157 riesgo #7, 176 riesgo #9 ("se mantiene anotado... plan futuro de masking") y 178 §7 ("Vigía de DATOS: excluido por PII y costo; si algún día se considera, requiere su propio plan con masking"). Nadie lo tomó; este plan lo cierra.
2. **El riesgo es real y verificado**: el data-diff del 126 trae VALORES CRUDOS de las tablas comparadas — `diff_table_data` normaliza y devuelve `only_source`/`only_target` como dicts fila columna→valor y `changed[].cells` con `source`/`target` (`services/dbcompare_data.py:177-188`) — y hoy viajan en claro por DOS rutas: `get_run_route` sirve el run entero con `jsonify(run)` (`api/db_compare.py:222-230`) y `list_runs_route` sirve la metadata de cada run, que EXCLUYE `diff` pero NO `data_diff` (`dbcompare_runs.py:227` — fix C1). Una tabla de parámetros RS con una columna de contraseña de servicio viaja hoy en claro a la UI por ambas.
3. **Nada en el repo lo cubre** (claims negativos con comando):
   - `grep -in "mask|redact"` sobre `api/db_compare.py` → **0 hits**.
   - `grep -rn "masking_prefs|dbcompare_masking"` sobre `backend/` → **0 hits**.
   - `grep -n "mask|redact|scrub"` sobre `services/dbcompare*.py` → **8 hits**, TODOS del `_scrub` de MENSAJES DE ERROR: `dbcompare_engine.py:78` (borra la password de la connection string en errores de conexión) y `dbcompare_runs.py:104` (ídem best-effort al persistir un run en error). **Distinción explícita**: ese scrub protege credenciales DE CONEXIÓN en textos de error; NINGÚN código enmascara valores DE FILAS en las respuestas del comparador.
4. **Desbloquea el futuro vigía de datos**: con masking de presentación operativo, un eventual plan de re-comparación programada de DATOS (extensión del 178) deja de estar bloqueado por PII.
5. **Onboarding casi nulo**: default ON, cero configuración; el operador solo nota puntos `••••` donde antes había un secreto — y un click lo revela si lo necesita.

---

## 2bis. Relación con 157 / 176 / 178 / 179 / 180 (intersección de archivos)

| Plan | Archivos que toca (según su doc) | Intersección con 181 |
|---|---|---|
| 157 (config UX) | `EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `dbcompare_config_import.py` (nuevo), `MigrationPanel.tsx` | NINGUNA |
| 176 (triage/gates/cierre) | `api/db_compare.py`, servicios nuevos, `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts`, `DataParitySection.tsx` (+ `tablePrefsLogic.ts`), `dbcompare_runs.py` (modo snapshot histórico) | `api/db_compare.py` (1 hunk) + `DataParitySection.tsx` (2 hunks) + `endpoints.ts` (append) + `dbcompare_runs.py` (zonas distintas) |
| 178 (radar/vigía) | `dbcompare_watch.py`/`dbcompare_baseline.py`/`api/db_compare_watch.py` (nuevos), `app.py`, `dbcompare_runs.py` (kwarg en `create_run:130` + dict `:154-162`), `endpoints.ts`, `DbComparePage.tsx` | `endpoints.ts` (append) + `dbcompare_runs.py` (zonas distintas) |
| 179 (snapshot v2) | `dbcompare_snapshot.py`, `dbcompare_diff.py`, registro de flags, +2 líneas declaradas en un test | NINGUNA |
| 180 (puente repo) | `dbcompare_repo_scripts.py`/`api/db_compare_repo.py` (nuevos), `DbComparePage.tsx`, `endpoints.ts` | `endpoints.ts` (append) |
| **181 (este)** | NUEVOS: `services/dbcompare_masking.py`, `api/db_compare_masking.py`, `DataMaskingBar.tsx`, `maskingLogic.ts`, `maskingLogic.test.ts`, 4 tests backend. EDITADOS: `api/db_compare.py` (SOLO `get_run_route`), **`services/dbcompare_runs.py` (SOLO 1 línea en `list_runs`, `:227` — fix C1)**, `api/__init__.py` (2 líneas), `DataParitySection.tsx` (2 hunks), `endpoints.ts` (append), `dbcompare.module.css` (append), `harness_flags.py`, `config.py`, `test_harness_flags_requires.py`, runners | — |

**Guía de merge anti-176/178 (los solapes reales, con zonas citadas):**

1. `api/db_compare.py` — este plan edita EXCLUSIVAMENTE el cuerpo de `get_run_route` (`:222-230`, 1 hunk de 2 líneas). Verificado (juez, grep): el doc del 176 tiene **0 menciones** de `get_run_route`; sus zonas declaradas en ese archivo son `start_data_diff_route` (`:410-411`) y rutas nuevas propias. Conflicto esperable: NINGUNO o adyacencia trivial; resolución: conservar ambos.
2. `services/dbcompare_runs.py` (**nuevo en v2, fix C1**) — este plan edita SOLO la línea del filtro de metadata en `list_runs` (`:227`: `{k: v for k, v in run.items() if k != "diff"}` → `if k not in ("diff", "data_diff")`). El 178 declara tocar la FIRMA de `create_run` (`:130`) y su dict (`:154-162`); el 176 declara "modo snapshot histórico" también alrededor de `create_run`. Zonas DISTINTAS de la `:227`; conflicto esperable: ninguno; ante adyacencia, conservar ambos y re-correr `tests/test_plan123_dbcompare_runs.py` + los tests de los otros planes.
3. `DataParitySection.tsx` — este plan edita SOLO la zona del render del sub-estado `done` (`:152-155`: import arriba + 1 JSX junto a `<DataDiffTables/>` en `:154`). Las zonas que el 176 declara tocar en ese archivo son OTRAS: el catch silencioso `:69` (doc 176 `:80,:822-824`) y el picker `:121-145` (doc 176 `:627`). Sin solape de líneas; resolución ante adyacencia: conservar ambos.
4. `endpoints.ts` — append de un objeto NUEVO al final del archivo real (hoy 4228 líneas; el último export actual es `Incidents`, `:4155` — verificar el final con `tail -n 3` / `Get-Content -Tail 3` al implementar). Gotcha conocido del repo (merge duplicado silencioso): tras cualquier merge, `npx tsc --noEmit` + `grep -c "export const DbCompareMasking" endpoints.ts` esperando exactamente 1.

**Nota de diseño sobre el hunk en `api/db_compare.py`** (por qué no cero, con alternativa descartada): `get_run_route:230` (`return jsonify(run)`) es donde el data-diff COMPLETO sale hacia la UI — interceptarlo con `after_request` obligaría a re-parsear el JSON ya serializado de TODAS las respuestas del blueprint (frágil y caro); la edición quirúrgica de 2 líneas en el punto de serialización es estrictamente menor. La lista de runs se protege en la FUENTE (`list_runs` deja de arrastrar `data_diff` — fix C1), que además es una mejora de payload por sí sola. El resto de la API nueva (prefs) va en blueprint propio `db_compare_masking` para NO engordar la colisión con el 176 (patrón ya establecido por 178/180).

---

## 3. Principios y guardarraíles

### 3.1 Doctrina presentación-vs-motor (literal) + tabla de superficies

El masking protege la PRESENTACIÓN, NUNCA el motor:

- El diff de datos compara valores REALES (`diff_table_data`, `services/dbcompare_data.py:87-211`) — enmascarar antes de comparar destruiría la detección. NO se toca.
- El run PERSISTE el data-diff crudo en disco (`run_data_diff` escribe "en el archivo del run", `services/dbcompare_data.py:215,219-239`) — límite v1 declarado (riesgo R3): disco local del operador mono-usuario, mismo perfil de riesgo que los snapshots ya persistidos por el 122.
- Los scripts DML del bundle (125/126) llevan valores REALES: son el artefacto de migración que el operador revisa y ejecuta; enmascararlos los rompería. El camino del bundle NO pasa por la respuesta HTTP del run: `generate_scripts_route` (`api/db_compare.py:260-277`) llama `generate_parity_bundle(run_id)` (`:274`) que RE-LEE el run desde disco por `run_id` (y `get_run` devuelve un dict FRESCO de disco por request — `_read_run` hace `json.loads` del archivo), y `emit_data_scripts` consume ese data-diff persistido (`services/dbcompare_scripts.py:568-651`). El masking vive SOLO en las superficies de presentación ⇒ los scripts quedan intactos POR CONSTRUCCIÓN (KPI-4 lo prueba byte a byte con orden GET→bundle).
- Revelar una columna enmascarada = 1 click del operador (override persistido en MaskingPrefs v1). Seguridad por default SIN pérdida de capacidad.

**[ADICIÓN ARQUITECTO] Tabla de superficies del data-diff (contrato de honestidad — fix C1/C2).** Cada superficie por la que valores de filas pueden llegar al operador, con su estado:

| Superficie | Estado con masking ON | Sello |
|---|---|---|
| `GET /runs/<id>` (run completo → grid) | ENMASCARADA (transformación de salida, F3) | KPI-1 |
| `GET /runs` (lista) | SIN data_diff — la metadata excluye `diff` Y `data_diff` (fix C1; antes filtraba solo `diff`) | KPI-8 |
| `POST /runs/<id>/data-diff` (arranque) | Ack de arranque sin filas (el resultado solo se ve por `GET /runs/<id>`) | KPI-8 (test) |
| `GET /runs/<id>/scripts/file` + `scripts.zip` (visor de scripts del bundle) | **NO CUBIERTA POR DOCTRINA**: los `.sql` llevan valores REALES (artefacto de migración) — el operador DEBE saberlo | Leyenda literal en la UI (F5) + smoke F6 |
| `GET /runs/<id>/export.md` | Sin filas de datos: el export imprime SOLO esquema (verificado `export_markdown`, `dbcompare_runs.py:265-321`) | R8 |
| Archivo del run en `data_dir()` (disco) | FUERA DE HTTP — crudo por diseño (límite v1) | R3 |

Regla para planes futuros: cualquier endpoint nuevo que sirva filas del data-diff DEBE pasar por `apply_to_run_response` (o transformación equivalente) y agregarse a esta tabla.

### 3.2 HITL, contratos y rieles

- **HITL**: enmascarar es el default seguro; REVELAR es siempre decisión humana explícita y queda persistida (auditable en `masking_prefs.json` con `updated_at`). Ninguna acción automática nueva.
- **Contratos congelados intactos**: DataDiff v1 (`dbcompare_data.py:197-211`) NO cambia — el masking es una TRANSFORMACIÓN DE SALIDA sobre una copia; el campo `masked_columns` es aditivo y existe SOLO en la respuesta HTTP, jamás en disco. La exclusión de `data_diff` en la METADATA de la lista (fix C1) no altera ningún contrato: la lista siempre fue "meta" (ya excluía `diff`) y ningún consumer del frontend lee `data_diff` desde la lista (el run completo se obtiene por `getRun` al seleccionar — `DbComparePage.tsx:93-102`). Snapshot v1, SchemaDiff v1 y Manifest v1: no se tocan.
- **Mono-operador sin auth real**: nada de RBAC; las prefs son un único archivo global.
- **3 runtimes**: feature de panel puro (Flask + React, sin LLM): idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro; fallback N/A.
- **No degradar**: con la flag OFF, respuesta byte-idéntica (KPI-2) y cero UI nueva; con ON, el costo de `apply_masking` está acotado por los caps ya existentes del 126: máx. 20 tablas por corrida (`_MAX_TABLES_PER_DATA_DIFF`, `dbcompare_data.py:25`) × máx. filas por lado `STACKY_DB_COMPARE_DATA_MAX_ROWS` (default 5000, `config.py:131-133`); la copia profunda SOLO sobre tablas con columnas masked; el polling de progreso NO paga costo (un run sin `data_diff` hace early-return — C10). Y la lista de runs pierde peso (fix C1).
- **Flags por UI**: registro completo (§3.4); pytest por archivo con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`; tests registrados en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20` + espejo `.ps1`).
- **Frontend sin RTL/jsdom**: lógica en `.ts` puros con vitest; CERO `style={{...}}`; tokens `--dbc-*` existentes.

### 3.3 Detectores v1 (decisiones con evidencia)

- **Por NOMBRE — tupla cerrada de regex case-insensitive** (`re.search` sobre el nombre de columna): `password|passwd|pwd`, `secret`, `token`, `api[_-]?key`, `contrase`, `credencial`, `conn(ection)?[_-]?str(ing)?`, `cadena[_-]?conexion`, `clave[_-]?(secreta|privada|api|acceso)`.
  - **Decisión evidenciada — `clave` a secas EXCLUIDA**: en el dominio RS "clave" significa KEY de parámetro (`services/glossary.py:33`: "Tabla maestra de parámetros del sistema. Cada parámetro tiene clave + ..."); enmascarar `CLAVE` mataría la utilidad principal del data-diff (tablas de parámetros clave/valor). Solo se enmascaran los compuestos inequívocos (`clave_secreta`, `clave_api`, `clave_privada`, `clave_acceso`).
  - Límite declarado: `token` matchea columnas legítimas del dominio (`TOKEN_TIMEOUT`, `TOKEN_PAGINACION`) — falso positivo aceptado v1, mitigado por revelar de 1 click persistido (R1).
- **Por VALOR — segunda línea, SOLO si el nombre no matcheó**: JWT (`^eyJ[A-Za-z0-9_-]{10,}\.`) y connection string embebida (`(?i)(password|pwd)\s*=`). **Y NADA MÁS en v1** — límites declarados: NO Luhn (los IDs numéricos largos de tablas de parámetros darían falsos positivos), NO emails (en tablas de parámetro suelen ser configuración legítima que el operador necesita ver). Decisión explícita, revisable en un plan futuro. El muestreo por valor está capado a 50 filas por lista y es DETERMINISTA: `only_source`/`only_target`/`changed` vienen ordenadas por PK (`dbcompare_data.py:168-170`, sorted), así que dos GETs del mismo run producen el mismo plan.

### 3.4 Flag

`STACKY_DB_COMPARE_MASKING_ENABLED`, bool, **default ON**. Justificación literal: AUMENTA la seguridad por default sin quitar ninguna capacidad (revelar = 1 click persistido); no conecta a nada, no publica nada, no escribe fuera de `data_dir()`, no tiene prerequisitos ⇒ NINGUNA de las 4 excepciones duras aplica. Registro completo: `FLAG_REGISTRY` con alta en `_CURATED_DEFAULTS_ON` (`harness_flags.py:310`, única vía de default ON), `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`), `requires="STACKY_DB_COMPARE_ENABLED"` (plano, profundidad 1), arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`, junto a `:183-185`), default efectivo en `config.py` con el idioma literal de `:119-133`, y `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py` (PROHIBIDO a mano).

---

## 4. Contrato MaskingPrefs v1

Persistencia: `data_dir()/db_compare/masking_prefs.json` (escritura atómica tmp + `os.replace`, mismo espíritu que `_write_bundle_atomic`, `dbcompare_scripts.py:706-723`). Subdirectorio consistente con `db_compare/{snapshots,runs,bundles}`.

```json
{
  "version": 1,
  "overrides": {
    "DBO.RUSUARIOS.PASSWORD": {"state": "visible", "updated_at": "2026-07-18T15:00:00Z"},
    "DBO.RPARAM.VALOR": {"state": "masked", "updated_at": "2026-07-18T15:05:00Z"}
  }
}
```

- **Clave CANÓNICA UPPERCASE** (fix C3): `"<SCHEMA>.<TABLE>.<COLUMN>"` — `set_override` normaliza a `.upper()` AL GUARDAR y `masking_plan` busca SOLO la forma upper. Motivo: SQL Server trae identificadores en case mixto y Oracle en upper; la clave canónica única hace el ida-vuelta determinista en ambos (la regla v1 de "2 intentos" era asimétrica y fallaba con prefs guardadas en mixto).
- `state`: `"visible"` (decisión humana de revelar — HITL) o `"masked"` (forzar aunque los detectores no lo atrapen). Un POST con `state: "auto"` ELIMINA el override (vuelve a detección automática).
- **Overrides huérfanos** (fix C7): un override cuya columna no aparece en el diff actual se IGNORA (inofensivo) y NO se limpia — la columna puede volver a aparecer en el próximo run; la limpieza manual es `state: "auto"`.
- Cero estado en memoria: las prefs se releen de disco en CADA aplicación (`load_prefs()` por request — el archivo es chico; esto garantiza KPI-3 sin caches ni invalidación).
- Archivo corrupto ⇒ `{}` (todo en automático = default SEGURO: enmascara de más, nunca de menos), sin crash, log warning.

---

## 5. Fases

Orden estricto: F0 → F1 → F2 → F3 → F4 → F5 → F6. TDD en cada una: escribir los tests nombrados, verlos fallar por la razón correcta, implementar, verlos pasar.

---

### F0 — Flag, config y arista

**Objetivo:** registrar `STACKY_DB_COMPARE_MASKING_ENABLED` (default ON) sin comportamiento nuevo.
**Valor:** kill-switch visible en el panel del arnés (categoría Comparador de BD) desde el día 0.

**Archivos a editar:** los 4 de siempre, con el idioma exacto verificado:
1. `services/harness_flags.py`: FlagSpec bool con `default=True` (comentario: "presentación protegida por default; revelar = 1 click persistido; ninguna excepción dura aplica"), después del último bloque `STACKY_DB_COMPARE_*` existente al implementar; alta en `_CURATED_DEFAULTS_ON`; key en `_CATEGORY_KEYS["comparador_bd"]`; `requires="STACKY_DB_COMPARE_ENABLED"`.
2. `config.py`: `STACKY_DB_COMPARE_MASKING_ENABLED: bool = os.getenv("STACKY_DB_COMPARE_MASKING_ENABLED", "true").strip().lower() == "true"` después del bloque del 126 (`:127-133`).
3. `tests/test_harness_flags_requires.py`: arista `"STACKY_DB_COMPARE_MASKING_ENABLED": "STACKY_DB_COMPARE_ENABLED",  # Plan 181` en `_REQUIRES_MAP_FROZEN` (`:120`, junto a `:183-185`).
4. Runners `run_harness_tests.sh` (`:20`) + `.ps1`: registrar los 4 tests nuevos (`tests/test_plan181_masking_core.py`, `test_plan181_prefs.py`, `test_plan181_response.py`, `test_plan181_api.py`).
5. Regenerar `harness_defaults.env` por script.

**Tests PRIMERO — `tests/test_plan181_api.py` (bloque flags):** `test_flag_registrada_bool_on_requires_master`, `test_flag_en_categoria`, `test_config_attr_existe_bool` (fix estilo 178/179: `isinstance(config.config.STACKY_DB_COMPARE_MASKING_ENABLED, bool)`; el valor efectivo del gate se testea en F3 vía `masking_enabled()` con monkeypatch — determinista, sin depender del env de la máquina).
**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_api.py -q` (+ `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`).
**Criterio (binario):** 3 nuevos + 2 preexistentes verdes; env regenerado.
**Flag:** la propia (sin efecto). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F1 — Núcleo puro: detectores, `mask_value`, `masking_plan`, `apply_masking`

**Objetivo:** toda la lógica de masking como funciones puras en el módulo nuevo, sin API ni disco.
**Valor:** corazón determinista, golden-testeable sin BD.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_masking.py`:

```python
"""Plan 181 — Masking determinista de secretos/PII en el data-diff (presentación).

DOCTRINA (doc 181 §3.1): protege la PRESENTACIÓN, nunca el motor. El diff compara
valores reales; el run persiste crudo; los scripts DML del bundle llevan valores
reales (generate_parity_bundle re-lee el run de disco: api/db_compare.py:274 ->
emit_data_scripts, dbcompare_scripts.py:568). Este módulo transforma COPIAS de la
respuesta HTTP y nada más. Revelar = override HITL persistido (MaskingPrefs v1).
Tabla de superficies cubiertas/no-cubiertas: doc 181 §3.1."""
from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

PREFS_VERSION = 1
MASKED_PLACEHOLDER = "••••"
_SUFFIX_MIN_LEN = 8  # fix C4: el sufijo de 2 chars SOLO si len>=8 (un secreto de
                     # 5-7 chars con sufijo revelaría hasta ~1/3 de su contenido)
_PREFS_LOCK = threading.Lock()

_NAME_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"password|passwd|pwd",
    r"secret",
    r"token",
    r"api[_-]?key",
    r"contrase",
    r"credencial",
    r"conn(ection)?[_-]?str(ing)?",
    r"cadena[_-]?conexion",
    r"clave[_-]?(secreta|privada|api|acceso)",  # 'clave' a secas EXCLUIDA (glossary.py:33: clave = key de parámetro RS)
))

_VALUE_PATTERNS = (
    re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\."),          # JWT
    re.compile(r"(password|pwd)\s*=", re.IGNORECASE),  # connection string embebida
)

_VALUE_SAMPLE_ROWS = 50  # muestreo determinista: las listas vienen ordenadas por PK
                         # (dbcompare_data.py:168-170) => mismo plan en cada GET


def column_name_is_sensitive(name: str) -> bool:
    return any(p.search(name or "") for p in _NAME_PATTERNS)


def value_is_sensitive(value) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(p.search(text) for p in _VALUE_PATTERNS)


def mask_value(value):
    """Regla EXACTA (golden, fix C4): None -> None (la nulidad no es secreto y el
    grid distingue NULL); len(str) < 8 -> '••••' pelado; si no -> '••••' + últimos
    2 chars (distinguibilidad sin revelar una fracción significativa)."""
    if value is None:
        return None
    text = str(value)
    if len(text) < _SUFFIX_MIN_LEN:
        return MASKED_PLACEHOLDER
    return MASKED_PLACEHOLDER + text[-2:]


def _override_key(schema: str, table: str, column: str) -> str:
    # Clave CANÓNICA UPPERCASE (fix C3): única forma guardada y única buscada.
    return f"{schema}.{table}.{column}".upper()


def masking_plan(table_diff: dict, prefs: dict) -> dict[str, str]:
    """dict columna -> 'masked'|'visible' para UN DataDiff v1 de tabla
    (shape dbcompare_data.py:197-211). Precedencia: override prefs > nombre >
    valor > visible. PURA: no lee disco."""
    schema = table_diff.get("schema") or ""
    table = table_diff.get("table") or ""
    overrides = prefs.get("overrides") or {}
    plan: dict[str, str] = {}
    for col in table_diff.get("columns") or []:
        override = overrides.get(_override_key(schema, table, col))
        if override and override.get("state") in ("visible", "masked"):
            plan[col] = override["state"]
            continue
        if column_name_is_sensitive(col):
            plan[col] = "masked"
            continue
        plan[col] = "visible"
    # Segunda línea por VALOR: solo columnas aún visibles sin override explícito.
    for col, state in plan.items():
        if state != "visible":
            continue
        if _override_key(schema, table, col) in overrides:
            continue  # el humano ya decidió: no re-enmascarar por valor
        if _any_sampled_value_sensitive(table_diff, col):
            plan[col] = "masked"
    return plan


def _any_sampled_value_sensitive(table_diff: dict, col: str) -> bool:
    for row in (table_diff.get("only_source") or [])[:_VALUE_SAMPLE_ROWS]:
        if value_is_sensitive(row.get(col)):
            return True
    for row in (table_diff.get("only_target") or [])[:_VALUE_SAMPLE_ROWS]:
        if value_is_sensitive(row.get(col)):
            return True
    for ch in (table_diff.get("changed") or [])[:_VALUE_SAMPLE_ROWS]:
        cell = (ch.get("cells") or {}).get(col)
        if cell and (value_is_sensitive(cell.get("source")) or value_is_sensitive(cell.get("target"))):
            return True
        if value_is_sensitive((ch.get("pk") or {}).get(col)):
            return True
    return False


def apply_masking(table_diff: dict, plan: dict[str, str]) -> dict:
    """Devuelve una COPIA del DataDiff de tabla con las columnas 'masked'
    enmascaradas en LAS CUATRO apariciones (KPI-1): filas planas de only_source
    y only_target (que mezclan pk+data cols, dbcompare_data.py:177-178),
    changed[].cells[col].source/target (:182-186) y changed[].pk[col] (:188).
    NO muta el original (KPI-6). Agrega masked_columns (aditivo, SOLO respuesta;
    con flag ON el campo está SIEMPRE — [] si nada se enmascaró, C9)."""
    masked_cols = sorted(c for c, s in plan.items() if s == "masked")
    if not masked_cols:
        out = dict(table_diff)
        out["masked_columns"] = []
        return out
    out = copy.deepcopy(table_diff)
    masked = set(masked_cols)
    for key in ("only_source", "only_target"):
        for row in out.get(key) or []:
            for col in list(row):
                if col in masked:
                    row[col] = mask_value(row[col])
    for ch in out.get("changed") or []:
        for col, cell in (ch.get("cells") or {}).items():
            if col in masked:
                cell["source"] = mask_value(cell.get("source"))
                cell["target"] = mask_value(cell.get("target"))
        pk = ch.get("pk") or {}
        for col in list(pk):
            if col in masked:
                pk[col] = mask_value(pk[col])
    out["masked_columns"] = masked_cols
    return out
```

**Tests PRIMERO — `tests/test_plan181_masking_core.py`** (todo con dicts a mano, sin disco):
- `test_nombres_sensibles_golden` (KPI-5): los 5 masked y los 4 visible del KPI, más `Contraseña`-sin-eñe (`CONTRASENA`) masked.
- `test_clave_a_secas_visible_compuestos_masked`: `CLAVE` visible; `CLAVE_SECRETA`, `ClaveApi` masked (decisión §3.3 con evidencia).
- `test_valores_sensibles_golden` (KPI-5): JWT y connstring masked; `hola`, `12345678`, `None` visible.
- `test_mask_value_regla_exacta` (fix C4): `None -> None`; `"abc" -> "••••"`; `"secret" -> "••••"` (6 chars, SIN sufijo); `"supersecret42" -> "••••42"` (13 chars, con sufijo).
- `test_plan_precedencia_override_gana`: override `visible` sobre columna `PASSWORD` ⇒ visible; override `masked` sobre `DESCRIPCION` ⇒ masked; override `visible` NO es re-enmascarado por la segunda línea de valor.
- `test_override_case_cruzado` (fix C3): override guardado para (`dbo`, `RUSUARIOS`, `Password`) aplica cuando el diff trae `schema="DBO", table="RUSUARIOS"` y columna `PASSWORD` (clave canónica upper en ambos lados).
- `test_plan_valor_solo_si_nombre_no_decidio`: columna `VALOR` con un JWT en la fila 1 ⇒ masked; el mismo JWT más allá de la fila 50 ⇒ visible (muestreo declarado y determinista).
- `test_apply_cuatro_apariciones` (KPI-1): fixture con la columna sensible presente en `only_source`, `only_target`, `changed.cells` y `changed.pk` ⇒ enmascarada en los 4 sitios; `masked_columns == ["PASSWORD"]`.
- `test_apply_no_muta_original` (KPI-6): deep-copy previa == original tras aplicar.
- `test_apply_sin_masked_no_copia_profunda`: con plan todo-visible, `out["only_source"] is table_diff["only_source"]` (misma referencia: cero costo) y `masked_columns == []`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_masking_core.py -q`
**Criterio (binario):** 10 tests verdes; el módulo no importa nada de conexión ni de Flask.
**Flag:** sin efecto (sin llamadores). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — MaskingPrefs v1: store en disco (atómico, sin cache, clave canónica)

**Objetivo:** `load_prefs()` / `set_override()` sobre `masking_prefs.json`.
**Valor:** la decisión humana de revelar/forzar queda persistida y sobrevive reinicios.

**Archivo a editar:** `services/dbcompare_masking.py` — agregar:

```python
def _prefs_path() -> Path:
    d = data_dir() / "db_compare"
    d.mkdir(parents=True, exist_ok=True)
    return d / "masking_prefs.json"


def load_prefs() -> dict:
    """SIEMPRE relee de disco (cero estado en memoria — KPI-3): el archivo es
    chico y esto garantiza que un override sobreviva reinicios sin caches."""
    path = _prefs_path()
    if not path.exists():
        return {"version": PREFS_VERSION, "overrides": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": PREFS_VERSION, "overrides": {}}
    if doc.get("version") != PREFS_VERSION or not isinstance(doc.get("overrides"), dict):
        return {"version": PREFS_VERSION, "overrides": {}}
    return doc


def set_override(schema: str, table: str, column: str, state: str) -> dict:
    """state: 'visible'|'masked' setea; 'auto' elimina el override. Retorna prefs.
    La clave se guarda SIEMPRE en su forma canónica UPPERCASE (fix C3)."""
    if state not in ("visible", "masked", "auto"):
        raise ValueError(f"state inválido: {state!r} (visible|masked|auto)")
    key = _override_key(schema, table, column)
    with _PREFS_LOCK:
        prefs = load_prefs()
        if state == "auto":
            prefs["overrides"].pop(key, None)
        else:
            prefs["overrides"][key] = {
                "state": state,
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        path = _prefs_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    return prefs
```

**Tests PRIMERO — `tests/test_plan181_prefs.py`** (monkeypatch `data_dir` → `tmp_path`, patrón de la serie):
- `test_prefs_vacias_por_default`.
- `test_set_visible_y_masked_persisten`: y las claves guardadas están en UPPERCASE aunque los args vengan en mixto (fix C3).
- `test_auto_elimina_override`: elimina también cuando el set original fue con case distinto (canónica).
- `test_override_visible_persiste_y_releen_disco` (KPI-3): `set_override(...)`; simular "reinicio" escribiendo por fuera y llamando `load_prefs()` de nuevo ⇒ el override está; NO existe ninguna variable de módulo con las prefs cacheadas (assert por inspección: `load_prefs` devuelve objetos NUEVOS en cada llamada — `load_prefs() is not load_prefs()`).
- `test_state_invalido_lanza`.
- `test_archivo_corrupto_degrada_vacio`.
- `test_escritura_atomica_sin_tmp`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_prefs.py -q`
**Criterio (binario):** 7 tests verdes.
**Flag:** aún sin efecto en respuestas. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — Transformación de salida: `apply_to_run_response` + hunk en `get_run_route` + sellado de la lista (fix C1)

**Objetivo:** que TODAS las superficies HTTP del data-diff queden protegidas: el run individual enmascarado con ON (byte-idéntico con OFF) y la lista de runs sin `data_diff` (siempre).
**Valor:** el KPI central del plan queda operativo con 2 líneas en la API existente + 1 línea en `list_runs`.

**Archivos a editar:**

1. `services/dbcompare_masking.py` — agregar:

```python
def masking_enabled() -> bool:
    import config as _config
    return bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)) and bool(
        getattr(_config.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False)
    )


def apply_to_run_response(run: dict) -> dict:
    """Punto de aplicación para el RUN COMPLETO (doc 181 §3.1, tabla de
    superficies). Con flag OFF o sin data_diff: retorna EL MISMO objeto sin copia
    ni campo aditivo => jsonify byte-idéntico a main (KPI-2). Con ON: copia
    superficial del run + data_diff transformado."""
    if not masking_enabled():
        return run
    data_diff = run.get("data_diff")
    if not data_diff or not isinstance(data_diff.get("tables"), dict):
        return run
    prefs = load_prefs()
    out_tables = {}
    for key, result in data_diff["tables"].items():
        if not isinstance(result, dict) or "error" in result or "columns" not in result:
            out_tables[key] = result  # errores y shapes no-diff pasan tal cual
            continue
        plan = masking_plan(result, prefs)
        out_tables[key] = apply_masking(result, plan)
    out_run = dict(run)
    out_data_diff = dict(data_diff)
    out_data_diff["tables"] = out_tables
    out_run["data_diff"] = out_data_diff
    return out_run
```

2. `api/db_compare.py` — hunk quirúrgico ÚNICO en `get_run_route` (`:222-230`): reemplazar `return jsonify(run)` (`:230`) por:

```python
    from services import dbcompare_masking
    return jsonify(dbcompare_masking.apply_to_run_response(run))
```

(el import puede ir arriba con los demás; el cuerpo del route no cambia en nada más.)

3. `services/dbcompare_runs.py` — **1 línea en `list_runs` (fix C1, KPI-8):** en `:227`, reemplazar
```python
        meta = {k: v for k, v in run.items() if k != "diff"}
```
por
```python
        meta = {k: v for k, v in run.items() if k not in ("diff", "data_diff")}  # Plan 181: la lista JAMÁS arrastra filas (los secretos crudos viajaban por acá) ni el peso del data-diff
```
Compat verificada: la lista siempre fue metadata (ya excluía `diff`); ningún consumer lee `data_diff` desde la lista — el frontend obtiene el run completo por `DbCompare.getRun` al seleccionar (`DbComparePage.tsx:93-102`) y `runHistory`/el radar del 178 (papel) usan `summary`. Esta línea protege la superficie INDEPENDIENTEMENTE de la flag de masking: es corrección de perímetro + peso de payload, no feature.

**Tests PRIMERO — `tests/test_plan181_response.py`** (cliente Flask + run sembrado en `tmp_path` con `data_diff` que contiene columna `PASSWORD` con valores reales):
- `test_password_enmascarada_en_respuesta` (KPI-1): GET run con ON ⇒ los valores de `PASSWORD` en `only_source`/`only_target`/`changed.cells`/`changed.pk` respetan `mask_value` y `masked_columns == ["PASSWORD"]`.
- `test_off_byte_identico` (KPI-2): con la flag OFF (monkeypatch `config.config`), `resp.get_data()` es EXACTAMENTE igual al de main (comparar contra un GET con la función anulada: monkeypatch `apply_to_run_response` a identidad ⇒ mismos bytes; y además `masked_columns` ausente).
- `test_list_runs_sin_data_diff` (KPI-8, fix C1): sembrar run con `data_diff` que contiene secretos ⇒ `GET /runs` responde la lista SIN la clave `data_diff` en ningún run (con flag ON y también con OFF — la exclusión es incondicional) y sin la clave `diff` (conducta preexistente intacta).
- `test_post_data_diff_no_sirve_filas` (KPI-8): la respuesta del `POST /runs/<id>/data-diff` (arranque) no contiene `only_source` ni `changed` ni `only_target` (es un ack; las filas solo se ven por el GET del run, ya protegido).
- `test_disco_retiene_crudo`: tras un GET con ON, releer el archivo del run en disco ⇒ los valores siguen CRUDOS (la transformación no toca persistencia).
- `test_bundle_dml_byte_identico_con_masking_on` (KPI-4, BLOQUEANTE, fix C5 — ORDEN OBLIGATORIO): (1) GET run con ON y assert de que la respuesta vino enmascarada; (2) RECIÉN ENTONCES `POST /runs/<id>/scripts`; (3) comparar los archivos DML byte a byte contra el bundle generado con OFF sobre el mismo run sembrado ⇒ idénticos y contienen el valor REAL de `PASSWORD`. El orden GET→bundle existe para detectar cualquier mutación accidental compartida.
- `test_tabla_con_error_pasa_tal_cual`: entrada de `tables` con `{"error": ...}` no se transforma ni rompe.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_response.py -q`
**Criterio (binario):** 7 tests verdes; `git diff` de `api/db_compare.py` muestra exactamente 1 hunk (más el import) SOLO en `get_run_route`; `git diff` de `dbcompare_runs.py` muestra exactamente 1 línea cambiada en `list_runs`.
**Flag:** gate dentro de `masking_enabled()` (hot-apply por request); la exclusión de `data_diff` en la lista es incondicional (perímetro). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — API de prefs: blueprint nuevo `db_compare_masking`

**Objetivo:** GET estado + POST override por columna, en blueprint propio (cero engorde de `api/db_compare.py`).
**Valor:** el click "Revelar/Ocultar" de la UI tiene backend.

**Archivo a crear:** `api/db_compare_masking.py` (patrón 178/180: mismo `url_prefix="/db-compare"`, nombre distinto; rutas nuevas sin colisión — la tabla de rutas existentes está verificada en `api/db_compare.py:52-411` y no incluye `/masking/*`):

```python
from flask import Blueprint, jsonify, request

import config as _config
from services import dbcompare_masking

bp = Blueprint("db_compare_masking", __name__, url_prefix="/db-compare")


def _require_masking_enabled():
    # Idioma api/db_compare.py:27-29 — instancia de flags = config.config.
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False):
        return jsonify({"ok": False, "error": "Masking deshabilitado (STACKY_DB_COMPARE_MASKING_ENABLED)."}), 403
    return None
```

| Método y ruta | Función | Comportamiento |
|---|---|---|
| `GET /masking/prefs` | `get_masking_prefs_route` | 200 `{"ok": true, "prefs": dbcompare_masking.load_prefs()}` |
| `POST /masking/prefs` | `post_masking_override_route` | body `{"schema","table","column","state"}` con `state ∈ visible|masked|auto` (**POST decidido en v2 — fix C8**: `api.post` existe con certeza en el helper del frontend); parsing defensivo `data = request.get_json(silent=True) or {}`; 400 ante `ValueError`, campos vacíos o body inválido; 200 `{"ok": true, "prefs": ...}` |

**Registro:** `api/__init__.py` — 2 líneas con el idioma de `:57` y `:118` (`from .db_compare_masking import bp as db_compare_masking_bp` + `api_bp.register_blueprint(db_compare_masking_bp)`).

**Tests PRIMERO — completar `tests/test_plan181_api.py`:**
- `test_403_master_off_y_masking_off`: ambas variantes ⇒ 403 en GET y POST.
- `test_get_prefs_vacias`.
- `test_post_visible_y_get_refleja`.
- `test_post_auto_borra`.
- `test_post_state_invalido_400`, `test_post_campos_vacios_400` y `test_post_body_no_json_400` (parsing defensivo).
- `test_post_luego_get_run_revela` (integración con F3): sembrar run con `PASSWORD`, POST `visible`, GET run ⇒ valores crudos y `masked_columns == []`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_api.py -q`
**Criterio (binario):** 8 tests de F4 (+3 de F0) verdes; `api/db_compare.py` sin cambios en esta fase.
**Flag:** doble gate 122+181. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F5 — Frontend: barra de masking con Revelar/Ocultar (2 hunks)

**Objetivo:** indicador de columnas enmascaradas + toggle por columna, con colisión mínima.
**Valor:** el HITL de revelar queda a 1 click, sin que el operador configure nada.

**Contexto verificado del grid:** los valores YA llegan enmascarados del backend (F3), así que el grid existente (`DataDiffTable`, `DataParitySection.tsx:178-216`) muestra `••••…` sin NINGÚN cambio. Lo único nuevo es la barra de control.

**Archivos a crear:**
1. `frontend/src/components/dbcompare/maskingLogic.ts` — puro:
   - Tipos locales: `MaskingPrefs`, `MaskedTableInfo { key: string; schema: string; table: string; maskedColumns: string[] }` (los tipos de `dataDiffLogic.ts`/`dbcompareTypes.ts` NO se editan: el campo `masked_columns` se lee con un cast local — TS estructural ignora campos extra).
   - `collectMaskedTables(tables: Record<string, unknown>): MaskedTableInfo[]` — recorre `dataDiff.tables`, parsea la clave `"schema.tabla"` (mismo split que `parseCandidateKey` de `dataDiffLogic.ts`, redefinido local para no tocar ese archivo) y junta `masked_columns` no vacías, orden estable por key.
   - `toggleLabel(state: "masked" | "visible"): string` — "Revelar" / "Ocultar".
2. `frontend/src/components/dbcompare/DataMaskingBar.tsx` — autocontenido:
   - Props: `{ tables: Record<string, unknown>; onChanged: () => void }`.
   - `collectMaskedTables(tables)`; si vacío ⇒ `return null` (cero UI cuando no hay nada enmascarado, y cero UI con flag OFF porque el backend no manda `masked_columns`).
   - Render: banda compacta "Columnas protegidas" + **leyenda fija de honestidad ([ADICIÓN ARQUITECTO], fix C2): "Los scripts del bundle contienen valores reales."** + por tabla, chips `schema.tabla.columna` con botón "Revelar" ⇒ `DbCompareMasking.putOverride({schema, table, column, state: "visible"})` + `onChanged()`; y un botón secundario "Ocultar de nuevo" (state `"auto"`) para volver al automático.
   - CERO `style={{...}}`; clases nuevas en `dbcompare.module.css` (append): `.maskingBar`, `.maskingChip`, `.maskingReveal`, `.maskingLegend`, con `var(--dbc-warn)` y `var(--dbc-unchanged)`.
3. `frontend/src/components/dbcompare/maskingLogic.test.ts` — vitest: `collectMaskedTables` (vacío ⇒ []; tablas con y sin `masked_columns`; parse de key con puntos solo en el primer separador), `toggleLabel`.

**Archivos a editar (mínimos):**
4. `frontend/src/api/endpoints.ts` — append AL FINAL REAL del archivo (hoy el último export es `Incidents`, `:4155`; verificar con `tail -n 3` / `Get-Content -Tail 3`; gotcha de merge §2bis):
   ```typescript
   // Plan 181 — Masking de secretos en el data-diff (prefs por columna).
   export const DbCompareMasking = {
     getPrefs: () => api.get<{ ok: boolean; prefs: MaskingPrefs }>("/api/db-compare/masking/prefs"),
     putOverride: (body: { schema: string; table: string; column: string; state: "visible" | "masked" | "auto" }) =>
       api.post<{ ok: boolean; prefs: MaskingPrefs }>("/api/db-compare/masking/prefs", body),
   };
   ```
   (tipo `MaskingPrefs` importado de `maskingLogic.ts`; el verbo es POST — decidido en v2, fix C8: `api.post` existe con certeza en el helper; el nombre `putOverride` se mantiene por semántica de dominio, el transporte es POST.)
5. `frontend/src/components/dbcompare/DataParitySection.tsx` — EXACTAMENTE 2 hunks en la zona `:152-155` (fuera de las zonas `:69` y `:121-145` que declara el 176 — §2bis):
   - 1 import: `import { DataMaskingBar } from "./DataMaskingBar";`
   - 1 JSX inmediatamente ANTES de la línea `{dataDiff && dataDiff.status === "done" && <DataDiffTables tables={dataDiff.tables} />}` (`:154`; si los números driftearon, el ancla es el TEXTO de esa línea, único en el archivo):
     ```tsx
     {dataDiff && dataDiff.status === "done" && (
       <DataMaskingBar
         tables={dataDiff.tables}
         onChanged={() => DbCompare.getRun(run.run_id).then(onRunUpdate).catch(() => undefined)}
       />
     )}
     ```

**Comandos:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/maskingLogic.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio (binario):** vitest verde; `tsc --noEmit` limpio; `grep -c "style={{" DataMaskingBar.tsx` == 0; `git diff` de `DataParitySection.tsx` = exactamente 2 hunks.
**Flag:** sin lectura de flags en frontend (la barra se auto-oculta sin `masked_columns`). **Runtimes:** idéntico. **Trabajo del operador:** ninguno (revelar es opcional, 1 click).

---

### F6 — Cierre y verificación integral

**Objetivo:** no-regresión y DoD auditable.

**Acciones:**
1. Registro de los 4 tests en ambos runners (grep de verificación).
2. Correr POR ARCHIVO: los 4 `test_plan181_*.py` + `tests/test_harness_flags.py` + `tests/test_harness_flags_requires.py` + los 6 preexistentes del KPI-7:
```bash
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan122_dbcompare_api.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan123_dbcompare_api.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan123_dbcompare_runs.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan126_dbcompare_data_api.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan126_dbcompare_data_diff.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan126_dbcompare_data_scripts.py -q
```
   (Nota de honestidad, patrón de la serie: si alguno fijara que `list_runs` incluye `data_diff`, se reporta como hallazgo y se re-evalúa el diseño de la exclusión — PROHIBIDO editar el test.)
3. `"./venv/Scripts/python.exe" -m compileall services/dbcompare_masking.py api/db_compare_masking.py` limpio (gotcha PyInstaller collect-submodules).
4. Frontend: `npx tsc --noEmit` + vitest del archivo.
5. Smoke manual documentado en el PR (BD real): comparar datos de una tabla con columna de password real ⇒ grid muestra `••••…` + barra "Columnas protegidas" con la leyenda de los scripts; la LISTA de runs no trae el data-diff (network tab: payload liviano); click "Revelar" ⇒ valores crudos tras el refresh; `data\db_compare\masking_prefs.json` contiene el override en clave UPPERCASE; generar scripts ⇒ el DML del bundle lleva el valor real y el visor de scripts lo MUESTRA real (superficie declarada, §3.1); apagar la flag por UI ⇒ todo en crudo sin barra.

**Criterio (binario):** puntos 1-4 verdes; punto 5 documentado.
**Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Falso positivo del detector oculta config legítima (p.ej. columna `TOKEN_TIMEOUT`) | El operador no ve un valor que necesita | Revelar = 1 click persistido (KPI-3); la tupla de nombres es cerrada y conservadora — `clave` a secas excluida con evidencia (`glossary.py:33`); el override queda en prefs para siempre |
| R2 | Falso negativo (secreto en columna de nombre neutro y valor no-JWT/no-connstring) | Secreto visible en UI | Límites v1 DECLARADOS (§3.3): segunda línea por valor cubre JWT/connstring; Luhn/emails son decisión explícita fuera de v1; el operador puede forzar `masked` por columna (POST state=masked) — HITL en ambas direcciones |
| R3 | El run en disco retiene los valores crudos | Secretos en `data_dir()` local | Límite v1 declarado (§3.1, tabla de superficies): disco local del operador mono-usuario, MISMO perfil de riesgo que los snapshots ya persistidos (122) y que los bundles DML (125/126) que por doctrina llevan valores reales; masking de persistencia queda en §7 |
| R4 | Colisión de merge con el 176/178 en `api/db_compare.py`, `dbcompare_runs.py` y `DataParitySection.tsx` | Conflictos o duplicado silencioso | Zonas citadas y disjuntas (§2bis: `get_run_route:222-230` — 0 menciones en doc 176; `list_runs:227` — fuera de las zonas `create_run` de 176/178; `DataParitySection:152-155` vs zonas 176 `:69`/`:121-145`); guía: conservar ambos + `tsc` + grep post-merge + re-correr `test_plan123_dbcompare_runs.py` |
| R5 | Performance de `apply_masking` en tablas grandes | GET del run más lento | Acotado por caps EXISTENTES del 126: ≤20 tablas (`dbcompare_data.py:25`) × ≤`STACKY_DB_COMPARE_DATA_MAX_ROWS` filas por lado (default 5000, `config.py:131-133`); la copia profunda ocurre SOLO en tablas con columnas masked (F1: sin masked ⇒ misma referencia); muestreo de valor capado a 50 filas por lista; el polling de progreso no paga costo (sin `data_diff` ⇒ early-return, C10); la lista de runs quedó MÁS liviana que en main (fix C1) |
| R6 | `masking_prefs.json` corrupto | Overrides perdidos temporalmente | Lectura defensiva ⇒ `{}` (vuelve a detección automática = default SEGURO: enmascara de más, nunca de menos), log warning, el próximo POST lo regenera |
| R7 | Sesión paralela ocupa el número 181 antes del commit | Colisión de numeración (precedente: 171) | Número recalculado listando `docs/` inmediatamente antes del Write; si al commitear existe otro 181, renumerar ANTES de commitear |
| R8 | El placeholder `••••` (no-ASCII) rompe algún consumer | Render extraño | Los valores del DataDiff ya son strings normalizados arbitrarios (`sqlvalues.normalize_value`, `dbcompare_data.py:162`) y el grid los muestra tal cual (`DataParitySection.tsx:207-208`); el export md del run NO imprime filas de datos (verificado `export_markdown`, `dbcompare_runs.py:265-321`: solo esquema) |
| R9 | **(v2, fix C6)** Enmascarar `changed[].pk` degrada la identidad visual de la fila (el operador no distingue QUÉ fila cambió) | Navegación del grid más difícil en tablas con PK sensible | Trade-off declarado y aceptado: una PK sensible ES un secreto (no enmascararla sería el agujero); mitigación: sufijo de 2 chars si len≥8 (distinguibilidad parcial) + revelar de 1 click persistido; el caso es raro (PKs sensibles no abundan en tablas de parámetros RS) |
| R10 | **(v2, fix C2)** El operador cree que el masking cubre TODO y el visor de scripts le muestra el secreto real | Falsa sensación de protección | Tabla de superficies como contrato (§3.1) + leyenda literal SIEMPRE visible en la barra de masking ("Los scripts del bundle contienen valores reales") + smoke F6 que lo verifica mirando el visor |

---

## 7. Fuera de scope (diferidos explícitos de este plan)

- **Masking de la PERSISTENCIA** (cifrar/enmascarar el data-diff dentro del archivo del run): fuera de v1 — declarado como límite con perfil de riesgo aceptado (R3); si algún día se hace, es un plan propio con migración de runs.
- **Masking de los scripts DML del bundle**: NUNCA — por doctrina (§3.1): son el artefacto de migración; enmascararlos los rompería. La superficie queda declarada en la tabla de §3.1 y la UI lo dice en la leyenda (R10).
- **Vigía de DATOS** (re-comparación programada de datos): plan futuro que ESTE plan desbloquea (178 §7); no se implementa acá.
- **Detectores Luhn/tarjetas y emails**: decisión explícita v1 (§3.3) — falsos positivos inaceptables en tablas de parámetros; revisable en un plan futuro con evidencia.
- **Masking en el export markdown del run**: innecesario — el export NO imprime filas de datos (`dbcompare_runs.py:265-321`, verificado); si un export de datos aparece en el futuro, DEBE pasar por `apply_to_run_response` o equivalente y sumarse a la tabla de superficies de §3.1 (regla declarada para ese plan futuro).
- **RBAC / masking por usuario**: no aplica (mono-operador sin auth real).

---

## 8. Glosario, orden de implementación y DoD global

### Glosario

- **Masking de presentación**: transformación de las RESPUESTAS HTTP (nunca del disco ni del motor) que reemplaza valores de columnas sensibles por `mask_value(...)`.
- **Tabla de superficies**: contrato de §3.1 que enumera CADA vía por la que valores de filas llegan al operador y su estado (cubierta / no cubierta por doctrina / fuera de HTTP).
- **Detector por nombre / por valor**: primera y segunda línea de decisión automática (§3.3); el valor solo se consulta si el nombre no decidió y no hay override.
- **Override**: decisión humana persistida por columna (`visible` | `masked`); `auto` la elimina. Clave canónica UPPERCASE (§4).
- **MaskingPrefs v1**: contrato del archivo de overrides (§4).
- **`masked_columns`**: campo ADITIVO por tabla que existe SOLO en la respuesta HTTP (con ON, siempre presente; `[]` si nada se enmascaró) — la señal que la UI usa para la barra de control.
- **Doctrina presentación-vs-motor**: §3.1 — la regla que hace compatibles seguridad por default y scripts útiles.

### Orden de implementación (estricto)

F0 (flag) → F1 (núcleo puro) → F2 (prefs) → F3 (respuesta + hunk API + sellado de lista) → F4 (API prefs) → F5 (frontend) → F6 (cierre). F2 depende solo de F0; F3 depende de F1+F2. Nada más es permutable.

### Definition of Done global

1. Los 8 KPIs de §1.2 verificados con sus tests/comandos (KPI-4 es BLOQUEANTE: sin bundle byte-idéntico no hay merge; KPI-8 sella el perímetro de la lista).
2. Los 4 `tests/test_plan181_*.py` verdes POR ARCHIVO y registrados en ambos runners.
3. Los 6 preexistentes del KPI-7 + `test_harness_flags*.py` verdes sin editar ninguno.
4. Frontend: vitest verde, `tsc --noEmit` limpio, 0 `style={{` en los `.tsx` nuevos.
5. `harness_defaults.env` regenerado por script (la flag nueva en `true`).
6. `git diff --stat` solo lista los archivos de la fila "181" de la tabla §2bis; en `api/db_compare.py` el único símbolo tocado es `get_run_route`; en `dbcompare_runs.py` la única línea tocada es la del filtro de `list_runs` (`:227`).
7. Con la flag OFF: respuesta del run byte-idéntica a main, cero UI nueva, cero archivos nuevos leídos — y la lista de runs SIN `data_diff` igual (la exclusión es de perímetro, incondicional).
8. Smoke manual de F6 documentado en el PR (incluye verificar el visor de scripts como superficie declarada).

---

**Changelog interno:** v1 (2026-07-18) — propuesta inicial. v2 (2026-07-18) — crítica del juez: C1 bloqueante (lista de runs servía el data-diff crudo — punto único falso) + C2-C10; tabla de superficies como contrato; clave canónica de prefs; mask_value con umbral; orden GET→bundle en KPI-4; POST decidido; ver CHANGELOG al inicio.
Auto-consistencia KPI↔spec v2 (pares re-verificados tras los fixes): KPI-1↔`apply_masking` cubre las 4 apariciones incluyendo `changed[].pk` (F1, shape verificado contra `dbcompare_data.py:177-188`); KPI-2↔early-return del MISMO objeto con flag OFF antes de cualquier copia (F3); KPI-3↔`load_prefs()` relee disco en cada aplicación (F2/§4); KPI-4↔cadena de disco verificada (`get_run`→`_read_run` fresco por request; `generate_parity_bundle(run_id)` re-lee por id) + orden GET→bundle en el test; KPI-5↔tupla de F1 exacta con `clave` a secas excluida; KPI-6↔deepcopy solo con masked, sin masked no hay transformación; KPI-8↔`list_runs:227` excluye `("diff", "data_diff")` y el POST de data-diff responde ack sin filas (tests de perímetro).
