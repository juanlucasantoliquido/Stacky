# Plan 176 — Comparador de BD: ciclo de migración curada — triage del diff, gates read-only de precondiciones y verificación de cierre

**Estado:** PROPUESTO (v1, 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`).
**Serie:** capa 3 del Comparador de BD. Capa 1 = serie 122-126 (motor, IMPLEMENTADA en `main`). Capa 2 = Plan 157 (config in-place + import web.config + Panel de Migración, CRITICADO v2 APROBADO-CON-CAMBIOS, **base comprometida aún sin implementar**). Este plan es la capa 3 y **NO duplica nada del 157**: el 157 arregla la *entrada* (registrar ambientes, credenciales, panel visible); el 176 arregla el *ciclo de trabajo* (curar el diff, verificar precondiciones, cerrar la migración).
**Relación con el 157 (explícita):** independiente en código — este plan NO toca `EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `MigrationPanel.tsx` ni `dbcompare_config_import.py` (archivos del 157, todavía inexistentes). Integración condicional declarada en F5/F7: si al implementar este plan el `MigrationPanel.tsx` del 157 ya existe, los botones de gates/cierre se montan TAMBIÉN ahí; si no existe, se montan en la vista de resultados actual (`DbComparePage.tsx`). Ninguna flag de este plan depende de flags del 157 (`requires` apunta solo al master `STACKY_DB_COMPARE_ENABLED`). Los dos planes pueden implementarse en cualquier orden.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-18 sobre el working tree. Rutas de código
> relativas a `Stacky Agents/`. Prohibido desviarse de los nombres exactos.

---

## 1. Título + objetivo + KPI

El operador usa el Comparador para llevar TEST al estado de DEV en el producto RS. El flujo real
que ejecuta hoy A MANO (prior art `N:\GIT\RS\RSPACIFICO\pipelines\scripts`) tiene 4 pasos que
Stacky **no cubre**:

1. **Triage humano del diff** — `output/DbCompare/PLAN-replay-a-TEST.md` mapea CADA diferencia a
   una decisión con nivel de confianza (CONFIRMADO / INFERIDO / EXCLUIDO) y exclusiones puntuales
   (una fila `dlgPrestamos/5283` se excluyó por ser un bug en DEV; otros ítems quedaron "requiere
   decisión de negocio"). Hoy Stacky genera script para TODO ítem del diff, sí o sí: no hay forma
   de excluir ni de anotar una decisión.
2. **Gates read-only antes de DDL riesgoso** — `Invoke-DevTestParityReplay.ps1` cuenta NULLs antes
   de un `ALTER ... NOT NULL` y duplicados antes de recrear una PK (pasos 1/2), y aborta todo si
   el backup no verifica counts (líneas 487-517). Stacky emite el `ALTER` con un comentario
   `-- AJUSTAR` (Plan 125 §F2) pero no genera ni evalúa la query de precondición.
3. **Claves naturales para tablas sin PK** — `Compare-DevTestDatabase.ps1` líneas 495-499
   (`FallbackKeyColumns`): `RCONTROLES` no tiene PK en el motor y se compara por clave natural
   elegida por el humano. Stacky 126 exige PK (`services/dbcompare_data.py:117`) → `RCONTROLES`
   hoy NO es comparable en datos. Además, el 126 §6 difirió explícitamente a v2 "marcar tablas de
   parámetros persistentemente": hoy el operador re-elige las ≤20 tablas EN CADA corrida.
4. **Verificación de cierre con expectativas** — el paso 5 del replay re-corre el compare y
   assertea que lo arreglado ya no difiera Y que lo excluido SIGA difiriendo como prueba de
   no-modificación (líneas 736-758). Stacky tiene delta vs corrida previa (`runHistory.ts`,
   Plan 124 F6) pero no expectativas.

Este plan agrega esas 4 capacidades + una tanda de potencia visual del diff, TODO sin ejecutar
jamás una escritura contra una BD (doctrina de la serie: Stacky GENERA, nunca ejecuta; el único
precedente de ejecución son SELECTs validados por `validate_select_only`,
`services/dbcompare_data.py:67`).

**KPIs (binarios):**

- **KPI-1 (triage):** con `STACKY_DB_COMPARE_TRIAGE_ENABLED` ON, marcar un ítem del diff como
  `excluido` y regenerar los scripts produce un bundle donde NINGÚN archivo contiene el DDL/DML de
  ese ítem, y el reporte `TRIAGE_EXCLUSIONS.md` lo lista con su nota (tests F1/F3).
- **KPI-2 (gates):** para un diff que incluye un cambio de nullability a NOT NULL, Stacky deriva la
  gate `SELECT COUNT(*) ... WHERE <col> IS NULL` sobre el DESTINO; el botón "Verificar
  precondiciones" la ejecuta read-only (pasando por `validate_select_only`) y pinta pass/fail; con
  NULLs > 0 el resultado es `fail` (tests F4/F5).
- **KPI-3 (claves naturales):** una tabla sin PK con clave natural definida por el operador se
  vuelve comparable en datos (caso `RCONTROLES`), y las tablas marcadas "de parámetro" aparecen
  preseleccionadas en el picker de datos (tests F6).
- **KPI-4 (cierre):** tras "Verificar migración" (re-compare del mismo par), cada ítem `confirmado`
  que ya no difiere = `ok`, cada `excluido` que sigue difiriendo = `ok`, y toda violación se lista
  en rojo (tests F7).
- **KPI-5 (compatibilidad):** con las 4 flags nuevas OFF, la API y la UI son idénticas a `main`
  (tests por fase). Además, con flags ON pero SIN decisiones de triage, el bundle generado es
  idéntico al de `main` (invariante F3).
- **KPI-6 (potencia visual):** el diff filtrado se exporta a CSV y JSON; las definiciones de vistas
  se comparan con diff por líneas resaltado; el wizard permite comparar dos snapshots históricos
  arbitrarios (tests F8).

## 2. Por qué ahora / gap que cierra

- La serie 122-126 dejó el motor completo y el 157 (aprobado) deja la puerta de entrada; lo que
  falta es exactamente el TRABAJO DIARIO del operador entre "vi el diff" y "migré y verifiqué".
  El prior art demuestra que ese trabajo hoy vive en un `.md` manual + scripts PowerShell ad-hoc.
- Diferidos explícitos que este plan salda: 126 §6 ("marcar tablas de parámetros
  persistentemente" — F6); la brecha #2/#4/#5 del prior art (gates, claves naturales,
  exclusión de filas) que ningún plan de la serie tomó.
- Fricciones UX medidas en el código actual que este plan elimina (F8): filtro de tipo
  mono-selección (`frontend/src/components/dbcompare/FiltersBar.tsx:48`); diff de vistas = dos
  `<pre>` crudos sin resaltado (`ObjectDrilldown.tsx:149-152`); sin export CSV/JSON del diff
  (solo `.md` del run completo, `SummaryHero.tsx:121`); imposible comparar snapshots históricos
  aunque la API los lista (`CompareWizard.tsx:138` solo fresh/cached vs
  `api/db_compare.py:162` `list_snapshots_route`); errores de fetch silenciosos
  (`DbComparePage.tsx:50,55`; `DataParitySection.tsx:69`).

## 3. Principios y guardarraíles (obligatorios en TODO el plan)

1. **Human-in-the-loop innegociable.** Stacky NUNCA ejecuta una escritura contra una BD. Las gates
   son SELECTs de solo lectura, se ejecutan ÚNICAMENTE cuando el operador aprieta "Verificar
   precondiciones" (nunca automáticas), y cada SELECT pasa por `validate_select_only` de
   `services/db_query.py` antes de ejecutarse (mismo guard que `dbcompare_data.py:67`). El triage
   lo decide el operador ítem por ítem; el default de todo ítem es `pendiente` y un ítem
   `pendiente` se comporta EXACTAMENTE como hoy (se emite su script). La verificación de cierre
   se lanza solo por click explícito.
2. **Contratos congelados: NO se tocan.** Snapshot v1 (122 §F3), SchemaDiff v1 + tabla cerrada
   `_KIND_SEVERITY` + semántica origen/destino (123 §F1, `services/dbcompare_diff.py:28`),
   Manifest v1 + REGLA DE ORO de backup pareado 1:1 (125 §F3, assert en
   `services/dbcompare_scripts.py:896`), DataDiff v1 + reglas literales de `dbcompare_sqlvalues`
   (126 §F1-F2). Este plan solo AGREGA contratos nuevos versionados (Triage v1, Gates v1,
   TablePrefs v1, ClosureReport v1) y campos ADITIVOS opcionales en respuestas existentes.
   Regla dura para el implementador: ningún campo existente cambia de nombre, tipo ni semántica.
3. **Config del operador SIEMPRE por UI.** Las 4 flags nuevas se registran en `FLAG_REGISTRY` y en
   `_CATEGORY_KEYS["comparador_bd"]` (`services/harness_flags.py:314`, tupla existente
   `:320-324`) → visibles y toggleables desde el panel de flags del arnés.
4. **Cero trabajo extra al operador / default ON.** Las 4 flags nacen default ON bajo el master
   `STACKY_DB_COMPARE_ENABLED` (ya ON, `backend/config.py:119-121`). Ninguna de las 4 excepciones
   duras aplica: (1) nada bypasea revisión humana — gates y cierre corren solo por click, el triage
   es decisión del humano; (2) nada es destructivo — todo es archivo JSON local reversible y
   SELECTs read-only; (3) sin prerequisitos nuevos — cero dependencias nuevas (stdlib + lo ya
   instalado); (4) no reduce seguridad — los SELECTs pasan por el guard existente. Sin decisiones
   del operador, el comportamiento es idéntico a `main`.
5. **Paridad de 3 runtimes.** Feature de PANEL (backend Flask + React), sin LLM y sin depender del
   runtime de agentes: idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro. Fallback por
   fase: N/A (no hay dependencia de runtime); si un driver de BD falta, aplica la degradación
   existente del comparador (aviso de drivers, `DbComparePage.tsx:129`).
6. **Mono-operador, sin auth.** Nada de RBAC. Los archivos de triage/prefs viven en
   `data_dir()/db_compare/` como el resto del estado del comparador.
7. **No degradar.** Con flags OFF: bit a bit como `main`. Escrituras de estado con patrón atómico
   tmp + `os.replace` (mismo patrón que `_write_bundle_atomic`,
   `services/dbcompare_scripts.py:706`). Sin dependencias nuevas de frontend ni backend.
8. **Gap RTL/jsdom (estructural, conocido):** los `.tsx` NO llevan tests de render; TODA la lógica
   de UI nueva va en helpers `.ts` puros con vitest por archivo + `npx tsc --noEmit`. Cero
   `style={{...}}` en `.tsx` nuevos (ratchet uiDebtRatchet): estilos en
   `dbcompare.module.css` con los tokens existentes (`--dbc-*`, DoD serie 124), y si hace falta
   estilo dinámico, ref + effect imperativo.
9. **Tests backend nuevos registrados en el ratchet:** cada `test_plan176_*.py` se agrega a
   `HARNESS_TEST_FILES` en `backend/scripts/run_harness_tests.sh:20` y su espejo `.ps1`
   (criterio: `test_harness_ratchet_meta.py` verde). Pytest SIEMPRE por archivo con el intérprete
   real del repo: `cd "Stacky Agents/backend"` y usar `./venv/Scripts/python.exe` si existe, si no
   `./.venv/Scripts/python.exe` (en ese orden, sin excepciones).

---

## 4. Fases

### F0 — Flags del arnés + health aditivo (fundación)

**Objetivo (1 frase):** declarar las 4 flags nuevas (default ON, `requires` al master) y exponerlas
aditivamente en `/health` para que el frontend gatee cada feature.
**Valor:** habilita todo el plan de forma togglable por UI y reversible por flag.

**Archivos a editar:**
- `backend/config.py`
- `backend/services/harness_flags.py`
- `backend/api/db_compare.py`
- `backend/tests/test_harness_flags_requires.py`
- `backend/scripts/run_harness_tests.sh` + `backend/scripts/run_harness_tests.ps1`

**Flags nuevas (nombres EXACTOS, todas `type="bool"`, `default=True`,
`requires="STACKY_DB_COMPARE_ENABLED"`, `group="comparador_bd"`):**
1. `STACKY_DB_COMPARE_TRIAGE_ENABLED` — triage del diff + bundle curado + verificación de cierre
   (F1, F2, F3, F7).
2. `STACKY_DB_COMPARE_GATES_ENABLED` — gates read-only de precondiciones (F4, F5).
3. `STACKY_DB_COMPARE_TABLE_PREFS_ENABLED` — tablas de parámetro persistentes + claves naturales
   (F6).
4. `STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED` — potencia visual del diff (F8).

**Cambios exactos:**

1. En `backend/config.py`, junto al bloque `STACKY_DB_COMPARE_*` existente (`config.py:119-133`),
   agregar 4 atributos replicando LITERALMENTE el idioma del bloque existente (verificar el
   operador `.strip().lower() == "true"` real en `config.py:119-121` y copiarlo):
```python
    STACKY_DB_COMPARE_TRIAGE_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_TRIAGE_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_DB_COMPARE_GATES_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_GATES_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_DB_COMPARE_TABLE_PREFS_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_TABLE_PREFS_ENABLED", "true"
    ).strip().lower() == "true"
    STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED: bool = os.getenv(
        "STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED", "true"
    ).strip().lower() == "true"
```
2. En `backend/services/harness_flags.py`, dentro de `FLAG_REGISTRY` (después del último
   `FlagSpec` del grupo `comparador_bd`, cerca de `harness_flags.py:3162-3175`), agregar 4
   `FlagSpec` con `key` exacta, `type="bool"`, `default=True`,
   `requires="STACKY_DB_COMPARE_ENABLED"`, `group="comparador_bd"` y labels:
   - "Triage del diff (curar qué migrar)" / description: "Permite marcar cada diferencia como
     confirmada o excluida con nota; los scripts respetan la curación y habilita la verificación
     de cierre de migración."
   - "Gates de precondiciones (solo lectura)" / description: "Deriva consultas SELECT de
     verificación previa para cambios riesgosos (NOT NULL, PK, UNIQUE) y permite ejecutarlas
     read-only con un click para ver pass/fail antes de migrar."
   - "Tablas de parámetro y claves naturales" / description: "Permite marcar tablas de parámetro
     (preseleccionadas al comparar datos) y definir una clave natural para tablas sin PK."
   - "Diff UX v2 (filtros múltiples, export, snapshots históricos)" / description: "Filtro
     multi-tipo, export CSV/JSON del diff filtrado, diff por líneas en vistas y comparación de
     snapshots históricos."
   **Gotcha obligatorio (Plan 63/122):** para `type="bool"` con `default=True` la vía canónica es
   `_CURATED_DEFAULTS_ON` (`harness_flags.py:328-335`); seguir el patrón EXACTO de
   `STACKY_DB_COMPARE_DATA_DIFF_ENABLED` (`harness_flags.py:3153-3161`).
3. En `_CATEGORY_KEYS["comparador_bd"]` (tupla que arranca en `harness_flags.py:314`), agregar las
   4 keys al final. Criterio: `test_every_registry_flag_is_categorized` verde.
4. En `backend/tests/test_harness_flags_requires.py`, agregar al dict `_REQUIRES_MAP_FROZEN` las 4
   entradas `"<KEY>": "STACKY_DB_COMPARE_ENABLED"` (aristas de profundidad 1; regla R4: jamás
   encadenar a una flag hija).
5. En `backend/api/db_compare.py`, en `health_route` (`api/db_compare.py:52-53`), agregar al dict
   de respuesta 4 keys ADITIVAS (sin tocar las existentes):
   `"triage_enabled"`, `"gates_enabled"`, `"table_prefs_enabled"`, `"diff_ux_v2_enabled"`,
   cada una leyendo `config.config.<FLAG>` (gotcha: la instancia de flags es `config.config`, NO
   el módulo `config`).

**Test PRIMERO (TDD):** `backend/tests/test_plan176_dbcompare_flags.py`
Casos:
- `test_las_cuatro_flags_existen_en_registry`
- `test_las_cuatro_flags_default_on`
- `test_las_cuatro_flags_requieren_master` (cada `requires == "STACKY_DB_COMPARE_ENABLED"`)
- `test_las_cuatro_flags_categorizadas_en_comparador_bd`
- `test_health_reporta_flags_nuevas` (con `app.test_client()`, GET `/api/db-compare/health`
  contiene las 4 keys nuevas booleanas y conserva `flag_enabled`/`data_diff_enabled`)
Comando:
```
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan176_dbcompare_flags.py tests/test_harness_flags_requires.py -q
```
**Criterio BINARIO:** ambos archivos verdes (exit 0), incluidos `test_requires_map_is_frozen` y
`test_every_registry_flag_is_categorized`.
**Flag:** N/A (esta fase ES las flags). **Impacto por runtime:** idéntico. Fallback: N/A.
**Trabajo del operador:** ninguno.
**Ratchet:** registrar `tests/test_plan176_dbcompare_flags.py` (y TODOS los `test_plan176_*.py` de
las fases siguientes, a medida que se crean) en `HARNESS_TEST_FILES`
(`run_harness_tests.sh:20` + espejo `.ps1`).

---

### F1 — Triage backend: decisiones por ítem, persistidas por corrida

**Objetivo (1 frase):** un servicio + 3 endpoints para registrar la decisión humana
(`confirmado` / `excluido` / `pendiente`) con nota por cada ítem del diff (de esquema y de datos),
persistida por `run_id`.
**Valor:** convierte el `PLAN-replay-a-TEST.md` manual del prior art en una capacidad del producto.

**Archivo a crear:** `backend/services/dbcompare_triage.py`
**Archivo a editar:** `backend/api/db_compare.py` (mismo blueprint `bp` de `api/db_compare.py:24`;
NO crear blueprint nuevo).

**Contrato Triage v1 (NUEVO, versionado — archivo `data_dir()/db_compare/triage/<run_id>.json`):**
```json
{
  "version": 1,
  "run_id": "run_..._src_vs_dst",
  "items": {
    "<item_key>": {"decision": "confirmado|excluido|pendiente", "note": "texto", "decided_at": "ISO-8601"}
  },
  "updated_at": "ISO-8601"
}
```
- `item_key` de ítem de ESQUEMA: `f"{object_type}:{schema}.{name}"` usando los campos EXACTOS del
  ítem de SchemaDiff v1 (`items[].object_type/schema/name`, contrato 123 §F1). Es estable entre
  corridas del mismo par (no incluye run_id ni timestamps).
- `item_key` de FILA de datos: `f"data:{schema}.{table}:{pk_canon}"` donde `pk_canon` =
  `json.dumps({col: normalize_value(valor)}, sort_keys=True, separators=(",", ":"))` reusando
  `normalize_value` (`services/dbcompare_sqlvalues.py:40`) para estabilidad determinista.
- Ítem ausente del dict = `pendiente` (default implícito; el archivo puede no existir).

**Símbolos EXACTOS en `dbcompare_triage.py`:**
- `DECISIONS = ("confirmado", "excluido", "pendiente")`
- `TRIAGE_VERSION = 1`
- `_NOTE_MAX_CHARS = 2000`
- `def item_key_for_schema_item(item: dict) -> str` — regla literal de arriba.
- `def item_key_for_data_row(schema: str, table: str, pk: dict) -> str` — regla literal de arriba.
- `def load_triage(run_id: str) -> dict` — devuelve el doc Triage v1; si el archivo no existe,
  devuelve `{"version": 1, "run_id": run_id, "items": {}, "updated_at": None}` (nunca lanza).
- `def set_decision(run_id: str, item_key: str, decision: str, note: str = "") -> dict` — valida
  `decision in DECISIONS` (si no, `ValueError`), trunca `note` a `_NOTE_MAX_CHARS`, setea
  `decided_at` a UTC ISO, escribe atómico (tmp + `os.replace`), devuelve el doc completo. Si
  `decision == "pendiente"`, ELIMINA la key del dict (volver a pendiente = borrar la decisión).
- `def triage_summary(triage: dict, total_items: int) -> dict` — devuelve
  `{"confirmado": n1, "excluido": n2, "pendiente": total_items - n1 - n2}`.
- `def excluded_keys(triage: dict) -> set[str]` — keys con decision == "excluido".

**Endpoints (en `api/db_compare.py`, todos gateados por `_require_enabled()`
(`api/db_compare.py:27`) + nueva `_require_triage_enabled()` que devuelve 403 si
`STACKY_DB_COMPARE_TRIAGE_ENABLED` OFF — leer con `config.config`, patrón de `_require_enabled`):**
- `GET /runs/<run_id>/triage` → `get_triage_route()`. 404 si `get_run(run_id)` (de
  `services/dbcompare_runs.py:207`) devuelve None; si no, `load_triage(run_id)` + campo aditivo
  `"summary"` calculado con `triage_summary` sobre `len(run["diff"]["items"])` cuando el run está
  `done` (si no está done, `summary` = None).
- `PUT /runs/<run_id>/triage/item` → `put_triage_item_route()`. Body JSON:
  `{"item_key": str, "decision": str, "note": str}`. Validaciones EN ORDEN: run existe (404);
  `decision` válida (400 `{"error":"decision_invalida"}`); run está `done` (409
  `{"error":"run_no_done"}`); `item_key` pertenece al run — para ítems de esquema debe estar en
  `{item_key_for_schema_item(i) for i in run["diff"]["items"]}`; para ítems `data:` se acepta si
  el prefijo `data:<schema>.<table>:` corresponde a una tabla presente en el data-diff del run si
  existe, y si el run no tiene data-diff se responde 404 `{"error":"item_desconocido"}`.
  Respuesta: el doc Triage v1 actualizado + `summary`.
- `GET /runs/<run_id>/triage/exclusions.md` → `get_triage_exclusions_route()`. Markdown
  determinista descargable (`Content-Disposition: attachment`, patrón de
  `export_run_markdown_route`, `api/db_compare.py:233-234`) listando cada ítem excluido con su
  nota y `decided_at`, ordenado por `item_key`. 404 si run inexistente; si no hay exclusiones,
  cuerpo con la línea literal `Sin exclusiones.`.

**Test PRIMERO (TDD):**
`backend/tests/test_plan176_dbcompare_triage.py` (servicio puro):
- `test_item_key_schema_estable_y_literal` — para un ítem `{object_type:"table", schema:"dbo",
  name:"RCONTROLES"}` la key es exactamente `"table:dbo.RCONTROLES"`.
- `test_item_key_data_canonico_ordenado` — pk `{"b":1,"a":"x"}` produce sufijo JSON con keys
  ordenadas y sin espacios.
- `test_load_sin_archivo_devuelve_vacio`
- `test_set_decision_persiste_y_es_atomico` — tras `set_decision`, `load_triage` devuelve la
  decisión; no queda archivo `.tmp`.
- `test_decision_invalida_lanza_valueerror`
- `test_volver_a_pendiente_borra_la_entrada`
- `test_note_se_trunca_a_2000`
- `test_summary_cuenta_bien`
`backend/tests/test_plan176_dbcompare_triage_api.py` (con `app.test_client()` y un run fixture
`done` construido con el patrón de `test_plan123_dbcompare_api.py`):
- `test_triage_403_si_flag_off`
- `test_get_triage_404_run_inexistente`
- `test_put_decision_y_get_roundtrip`
- `test_put_item_key_desconocida_404`
- `test_put_run_no_done_409`
- `test_exclusions_md_lista_notas`
Comando (por archivo):
```
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan176_dbcompare_triage.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan176_dbcompare_triage_api.py -q
```
**Criterio BINARIO:** ambos archivos verdes.
**Flag:** `STACKY_DB_COMPARE_TRIAGE_ENABLED` (default ON; con OFF los 3 endpoints devuelven 403 y
nada más cambia).
**Impacto por runtime:** idéntico (Flask local). Fallback: N/A.
**Trabajo del operador:** ninguno (decidir es opcional; sin decisiones todo sigue igual).

---

### F2 — Triage UI: decidir desde la lista y el drill-down

**Objetivo (1 frase):** controles de decisión (Confirmar / Excluir / Pendiente + nota) en cada fila
del diff y en el drill-down, con resumen de curación en el hero.
**Valor:** el operador cura el diff donde lo está mirando, sin salir a un documento externo.

**Archivos a crear:**
- `frontend/src/components/dbcompare/triageLogic.ts` (lógica pura testeable)
**Archivos a editar:**
- `frontend/src/components/dbcompare/DiffList.tsx` (agregar celda de decisión por fila)
- `frontend/src/components/dbcompare/ObjectDrilldown.tsx` (bloque de decisión + nota)
- `frontend/src/components/dbcompare/SummaryHero.tsx` (chips de resumen:
  `N confirmados · N excluidos · N pendientes`)
- `frontend/src/components/dbcompare/DbComparePage.tsx` (estado `triage` + fetch/put)
- `frontend/src/api/endpoints.ts` (namespace `DbCompare`: agregar `getTriage(runId)`,
  `putTriageItem(runId, payload)`, `triageExclusionsUrl(runId)` siguiendo el patrón de los
  métodos DbCompare existentes importados en `DbComparePage.tsx:2`)
- `frontend/src/components/dbcompare/dbcompare.module.css` (estilos con tokens `--dbc-*`
  existentes; cero hex nuevos en `.tsx`, cero `style={{...}}`)

**Lógica pura (`triageLogic.ts`, símbolos EXACTOS):**
- `export type TriageDecision = "confirmado" | "excluido" | "pendiente";`
- `export function decisionFor(triage: TriageDoc | null, itemKey: string): TriageDecision` —
  ausente ⇒ `"pendiente"`.
- `export function cycleDecision(current: TriageDecision): TriageDecision` — orden literal
  `pendiente → confirmado → excluido → pendiente`.
- `export function itemKeyForSchemaItem(item: {object_type: string; schema: string; name: string}): string`
  — ESPEJO EXACTO de `item_key_for_schema_item` del backend (mismo formato).
- `export function summarizeTriage(triage: TriageDoc | null, totalItems: number): {confirmado: number; excluido: number; pendiente: number}`
- `export function decisionBadgeClass(d: TriageDecision): string` — nombres de clase CSS module:
  `"triageConfirmado" | "triageExcluido" | "triagePendiente"`.

**Diseño de UI (literal):**
- `DiffList.tsx`: nueva última celda por fila con un botón compacto que muestra la decisión actual
  (`✔ Confirmado` / `✖ Excluido` / `— Pendiente`) y al click cicla con `cycleDecision`, llamando
  `DbCompare.putTriageItem`. Si la flag está OFF (según `health.triage_enabled`), la celda NO se
  renderiza (lista idéntica a `main`).
- `ObjectDrilldown.tsx`: bloque bajo el título con los 3 estados como radio + `<textarea>` de nota
  (guardar en blur o botón "Guardar nota"); mismo gate por `health.triage_enabled`.
- `SummaryHero.tsx`: fila de 3 chips con el resumen (`summarizeTriage`); chip clickeable NO filtra
  en esta fase (solo informativo).
- `DbComparePage.tsx`: al entrar en vista `results` de un run `done` y flag ON, fetch
  `DbCompare.getTriage(runId)`; el estado `triage` se pasa como prop a DiffList / ObjectDrilldown /
  SummaryHero; tras cada `putTriageItem` exitoso se reemplaza el estado con la respuesta.

**Test PRIMERO (TDD, vitest puro):**
`frontend/src/components/dbcompare/__tests__/triageLogic.test.ts`
Casos: `decisionFor` default pendiente; `cycleDecision` cicla en el orden literal;
`itemKeyForSchemaItem` produce `"table:dbo.RCONTROLES"` (paridad con backend);
`summarizeTriage` con doc null y con decisiones mixtas.
Comando:
```
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/triageLogic.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** vitest de ese archivo verde + `tsc --noEmit` con 0 errores.
**Flag:** `STACKY_DB_COMPARE_TRIAGE_ENABLED` vía `health.triage_enabled` (la UI solo consulta
`/health`, sin lógica de flags duplicada).
**Impacto por runtime:** idéntico. Fallback: con flag OFF, UI idéntica a `main`.
**Trabajo del operador:** ninguno.

---

### F3 — El bundle de scripts respeta el triage (curación efectiva)

**Objetivo (1 frase):** los ítems/filas `excluido` NO emiten scripts en el bundle del Plan 125/126,
y el bundle incluye un `TRIAGE_EXCLUSIONS.md` con lo excluido y sus notas.
**Valor:** la decisión humana se vuelve efectiva sin editar SQL a mano (hoy el operador debe borrar
bloques del script generado).

**Archivos a editar:**
- `backend/services/dbcompare_scripts.py`
- `backend/api/db_compare.py` (allowlist del visor de archivos)

**Cambios exactos (todos ADITIVOS, sin tocar Manifest v1):**
1. Nueva función pura en `dbcompare_scripts.py`:
   `def filter_pieces_by_triage(pieces: list, excluded: set[str]) -> tuple[list, list]` —
   recibe la salida de `flatten_diff` (`dbcompare_scripts.py:42`; cada pieza porta
   `object_type/schema/name` según el contrato del 125 §F2) y devuelve
   `(piezas_mantenidas, piezas_excluidas)` usando `item_key_for_schema_item` (importar de
   `services.dbcompare_triage`) sobre cada pieza. Determinista, sin I/O.
2. Nueva función pura: `def filter_data_rows_by_triage(table_diff: dict, excluded: set[str]) -> dict`
   — copia del DataDiff v1 de la tabla donde `only_source`, `only_target` y `changed` quedan sin
   las filas cuya `item_key_for_data_row(schema, table, pk)` esté en `excluded`. NO muta el
   original. Si tras filtrar la tabla queda sin filas en las 3 listas, la tabla no emite DML (y por
   la REGLA DE ORO tampoco requiere backup: ningún script la modifica).
3. `generate_parity_bundle(run_id, ...)` (`dbcompare_scripts.py:952`) y
   `generate_parity_bundle_from_diff(...)` (`:726`): nuevo parámetro keyword-only
   `excluded_keys: set[str] | None = None` (default None = comportamiento EXACTO de `main`).
   Cuando no es None: aplicar `filter_pieces_by_triage` ANTES de `emit_parity`/`emit_resguardo`
   (`:178`/`:462`) y `filter_data_rows_by_triage` ANTES de `emit_data_scripts` (`:568`). El
   pareo backup/rollback y el assert del invariante (`:896`) operan sobre las piezas YA filtradas
   ⇒ la REGLA DE ORO se preserva sin cambios.
4. Si hubo exclusiones (`piezas_excluidas` no vacía o filas de datos excluidas), escribir en la
   raíz del bundle el archivo `TRIAGE_EXCLUSIONS.md` (contenido determinista: un ítem por línea
   `- <item_key> — <note> (<decided_at>)`, ordenado por `item_key`). Este archivo NO se agrega a
   `entries` del manifest (Manifest v1 intacto); entra al `.zip` automáticamente porque
   `bundle_zip_bytes` (`:932`) zipea el directorio completo.
5. En `api/db_compare.py`, `_scrips_allowlist` — nombre real `_scripts_allowlist`
   (`api/db_compare.py:294`) — extender ADITIVAMENTE: al set derivado del manifest, agregar el
   literal `"TRIAGE_EXCLUSIONS.md"` para que `get_scripts_file_route` (`:305-306`) pueda servirlo.
   El guard anti-traversal existente (`:311`) no se toca.
6. En `generate_scripts_route` (`api/db_compare.py:260-261`): si
   `STACKY_DB_COMPARE_TRIAGE_ENABLED` ON, cargar `excluded_keys(load_triage(run_id))` y pasarlo a
   `generate_parity_bundle`; agregar a la respuesta el campo ADITIVO
   `"triage_applied": {"excluded_count": n}` (n=0 cuando no hay exclusiones). Con flag OFF:
   `excluded_keys=None` (idéntico a `main`).

**Test PRIMERO (TDD):** `backend/tests/test_plan176_dbcompare_triage_bundle.py`
(reusar fixtures de `backend/tests/_plan125_fixtures.py`):
- `test_sin_triage_bundle_identico` — con `excluded_keys=None` y con `set()` vacío, el manifest y
  el contenido de TODOS los archivos emitidos son idénticos a los de `main` (comparar con una
  generación sin parámetro). **Bloqueante (KPI-5).**
- `test_item_excluido_no_emite_script` — excluir una tabla del fixture ⇒ ningún archivo del bundle
  contiene su nombre calificado (`qualified`, `services/dbcompare_sqlnames.py:30`). **Bloqueante
  (KPI-1).**
- `test_exclusiones_md_presente_y_ordenado`
- `test_regla_de_oro_se_mantiene_con_exclusiones` — el assert del invariante (`:896`) pasa con
  piezas filtradas (ítem destructivo excluido ⇒ ni script ni backup).
- `test_fila_datos_excluida_no_emite_dml` — una fila `only_source` excluida no aparece en
  `03_datos/`.
- `test_endpoint_scripts_file_sirve_exclusions_md` — GET
  `/runs/<id>/scripts/file?path=TRIAGE_EXCLUSIONS.md` responde 200 tras generar con exclusiones.
Comando:
```
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan176_dbcompare_triage_bundle.py -q
```
**Criterio BINARIO:** todos verdes; los 2 marcados Bloqueante son innegociables.
**Flag:** `STACKY_DB_COMPARE_TRIAGE_ENABLED`. **Impacto por runtime:** idéntico. Fallback: con flag
OFF o sin decisiones, bundle idéntico a `main`.
**Trabajo del operador:** ninguno (regenerar scripts ya es acción explícita existente).

---

### F4 — Gates read-only de precondiciones (backend)

**Objetivo (1 frase):** derivar de un SchemaDiff las consultas SELECT de precondición para cambios
riesgosos, ejecutarlas SOLO a pedido del operador (read-only, guard `validate_select_only`) y
persistir pass/fail por gate.
**Valor:** porta al producto los pasos 1/2 del replay de Pacífico (contar NULLs antes de
`NOT NULL`, duplicados antes de PK/UNIQUE) que hoy viven en PowerShell manual.

**Archivo a crear:** `backend/services/dbcompare_gates.py`
**Archivo a editar:** `backend/api/db_compare.py`

**Contrato Gates v1 (NUEVO, versionado):**
- Gate = `{"gate_id": str, "item_key": str, "kind": str, "description": str, "sql": str,
  "check": "expect_zero" | "info_rowcount", "target_alias": str}`.
- Resultado (persistido en `data_dir()/db_compare/gates/<run_id>.json`):
  `{"version": 1, "run_id": ..., "results": {"<gate_id>": {"status": "pass|fail|error|info",
  "value": int | null, "detail": str, "checked_at": "ISO"}}}`.
- `gate_id` = `f"g{seq:03d}_{kind}_{schema}.{name}"` con `seq` = orden de derivación
  (determinista: ítems en el orden de `diff["items"]`).

**Símbolos EXACTOS en `dbcompare_gates.py`:**
- `GATES_VERSION = 1`
- `_MAX_GATES_PER_EVAL = 50`
- `_GATE_RULES: dict[str, str]` — tabla CERRADA kind → tipo de gate. Contenido conceptual (los
  NOMBRES de kind se copian LITERALES de `_KIND_SEVERITY`, `services/dbcompare_diff.py:28`; el
  implementador NO inventa nombres — el test anti-drift de abajo lo fuerza):
  1. kind de nullability que pasa a NOT NULL en el destino → `"null_count"` (gate:
     `SELECT COUNT(*) FROM <schema>.<tabla> WHERE <col> IS NULL`, check `expect_zero`).
  2. kind de PK agregada/cambiada → `"duplicate_key"` (gate:
     `SELECT COUNT(*) FROM (SELECT <pkcols> FROM <schema>.<tabla> GROUP BY <pkcols> HAVING COUNT(*) > 1) t`,
     check `expect_zero`; en Oracle el alias `t` se omite — regla literal por dialecto).
  3. kind de UNIQUE agregada → `"duplicate_key"` sobre las columnas del unique (ídem 2).
  4. kind de tabla eliminada en destino (DROP) → `"rowcount"` (gate:
     `SELECT COUNT(*) FROM <schema>.<tabla>`, check `info_rowcount` — informativo, nunca fail).
  Todo kind NO listado ⇒ sin gate. Identificadores SIEMPRE citados con `quote_ident` /
  `qualified` (`services/dbcompare_sqlnames.py:20/:30`).
- `def derive_gates(diff: dict, target_alias: str) -> list[dict]` — pura, determinista, sin I/O.
  Las columnas/pkcols se leen del detalle del ítem de SchemaDiff v1 (campo `changes[].detail` y
  el snapshot del run si el detail no alcanza; el implementador usa `run["diff"]` +
  `load_snapshot` (`services/dbcompare_snapshot.py:261`) del snapshot TARGET del run para obtener
  las columnas de PK/UNIQUE cuando el detail no las trae).
- `def evaluate_gates(run_id: str, gate_ids: list[str] | None) -> dict` — carga el run
  (`get_run`, `dbcompare_runs.py:207`; debe estar `done`, si no `ValueError`), deriva gates,
  filtra por `gate_ids` si no es None, cap `_MAX_GATES_PER_EVAL` (exceso ⇒ `ValueError`), y por
  cada gate: (i) `validate_select_only(sql)` de `services/db_query.py` — si falla, status
  `error` sin ejecutar; (ii) ejecutar con `open_engine(target_alias)`
  (`services/dbcompare_engine.py:88`, read-only, pool 1) con el timeout existente
  (`STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC`); (iii) status: `expect_zero` ⇒ `pass` si el escalar
  es 0, `fail` si > 0; `info_rowcount` ⇒ `info` con `value`; excepción de conexión ⇒ `error` con
  `detail` scrubbed (patrón `_scrub`, `dbcompare_engine.py:78`). Persiste atómico y devuelve el
  doc de resultados.
- `def gates_export_sql(diff: dict, target_alias: str, engine: str) -> str` — string único con
  todas las gates como SQL comentado (`-- GATE <gate_id>: <description>` + `-- esperado: 0` para
  `expect_zero`), determinista, para descargar.

**Endpoints (gate `_require_enabled()` + nueva `_require_gates_enabled()` → 403 si
`STACKY_DB_COMPARE_GATES_ENABLED` OFF):**
- `GET /runs/<run_id>/gates` → `get_gates_route()`. 404 run inexistente; 409 run no `done`.
  Respuesta: `{"gates": derive_gates(...), "results": <doc persistido o {}>}`.
- `POST /runs/<run_id>/gates/evaluate` → `evaluate_gates_route()`. Body opcional
  `{"gate_ids": [...]}`. **SOLO se ejecuta por este POST explícito del operador (HITL); ningún
  código lo llama automáticamente.** 404/409 como arriba; 400 si `gate_ids` excede el cap.
- `GET /runs/<run_id>/gates/export.sql` → `get_gates_export_route()`. Texto SQL descargable
  (`Content-Disposition: attachment`), 404/409 como arriba. **Las gates NO entran al bundle ZIP
  del 125** (cero riesgo sobre Manifest v1): son un artefacto propio descargable.

**Test PRIMERO (TDD):**
`backend/tests/test_plan176_dbcompare_gates.py` (puro):
- `test_gate_kinds_existen_en_kind_severity` — **anti-drift bloqueante:** toda key de
  `_GATE_RULES` ∈ `_KIND_SEVERITY` (import real de `services.dbcompare_diff`). Si un nombre de
  kind fue mal copiado, este test falla.
- `test_nullability_deriva_gate_null_count` — SQL golden exacto (con `quote_ident`).
- `test_pk_y_unique_derivan_duplicate_key` — SQL golden por dialecto (sqlserver con alias `t`,
  oracle sin alias).
- `test_table_removed_deriva_info_rowcount`
- `test_kind_no_listado_no_deriva_gate`
- `test_derivacion_determinista` — dos llamadas producen listas idénticas (mismos `gate_id`).
- `test_export_sql_determinista_y_comentado`
`backend/tests/test_plan176_dbcompare_gates_api.py` (test_client + ambiente sqlite `test-` — los
alias `test-*` habilitan sqlite, `services/dbcompare_registry.py:80` — con una tabla con NULLs
sembrados):
- `test_gates_403_si_flag_off`
- `test_get_gates_409_run_no_done`
- `test_evaluate_pasa_por_validate_select_only` — monkeypatch de
  `services.db_query.validate_select_only` que registra invocaciones ⇒ se llamó una vez por gate
  ejecutada. **Bloqueante (seguridad).**
- `test_evaluate_null_count_fail_con_nulls` — tabla sqlite con NULLs ⇒ status `fail`, `value` > 0.
- `test_evaluate_pass_sin_nulls`
- `test_resultados_persisten_y_get_los_devuelve`
- `test_cap_50_gates_400`
Comando (por archivo):
```
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan176_dbcompare_gates.py -q
cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan176_dbcompare_gates_api.py -q
```
**Criterio BINARIO:** todos verdes; `test_gate_kinds_existen_en_kind_severity` y
`test_evaluate_pasa_por_validate_select_only` son bloqueantes.
**Flag:** `STACKY_DB_COMPARE_GATES_ENABLED` (default ON; la EJECUCIÓN es siempre por click — no
aplica excepción dura 1 porque no hay acción automática).
**Impacto por runtime:** idéntico. Fallback: si el driver del engine falta, la evaluación devuelve
status `error` con detail scrubbed (la derivación y el export.sql funcionan igual, son puros).
**Trabajo del operador:** ninguno (usar las gates es opcional).

---

### F5 — Gates UI: panel de precondiciones en resultados

**Objetivo (1 frase):** un panel "Precondiciones de migración" en la vista de resultados con la
lista de gates, botón único "Verificar precondiciones" y semáforo por gate.
**Valor:** el operador ve verde/rojo ANTES de ejecutar cualquier script, sin abrir un cliente SQL.

**Archivos a crear:**
- `frontend/src/components/dbcompare/GatesPanel.tsx`
- `frontend/src/components/dbcompare/gatesLogic.ts`
**Archivos a editar:**
- `frontend/src/components/dbcompare/DbComparePage.tsx` (montar `<GatesPanel>` en la vista
  `results`, debajo de `SummaryHero`)
- `frontend/src/api/endpoints.ts` (`DbCompare.getGates(runId)`, `DbCompare.evaluateGates(runId,
  payload)`, `DbCompare.gatesExportUrl(runId)`)
- `frontend/src/components/dbcompare/dbcompare.module.css`

**Lógica pura (`gatesLogic.ts`, símbolos EXACTOS):**
- `export function statusFor(gate: Gate, results: GatesResults | null): "pass" | "fail" | "error" | "info" | "sin_verificar"`
- `export function overallStatus(gates: Gate[], results: GatesResults | null): "todo_pass" | "hay_fail" | "sin_verificar" | "sin_gates"`
  — `hay_fail` si al menos una gate `expect_zero` está `fail` o `error`; `todo_pass` si todas las
  `expect_zero` están `pass`; `sin_gates` si la lista está vacía.
- `export function statusLabel(s: ReturnType<typeof statusFor>): string` — textos literales:
  `pass → "OK"`, `fail → "FALLA"`, `error → "ERROR"`, `info → "INFO"`,
  `sin_verificar → "Sin verificar"`.

**Diseño de UI (literal):**
- Panel titulado "Precondiciones de migración (solo lectura)" con: descripción de cada gate, su
  SQL en `<code>` colapsable (`<details>`), semáforo por gate, botón primario "Verificar
  precondiciones" (POST evaluate; deshabilitado mientras corre, con spinner del sistema), link
  "Descargar gates (.sql)" (`gatesExportUrl`). Banner fijo con el texto EXACTO: "Estas consultas
  son de solo lectura. Stacky nunca ejecuta scripts de migración: los generás, los revisás y los
  corrés vos."
- Si `overallStatus === "hay_fail"`, mostrar aviso: "Hay precondiciones que fallan: revisá antes
  de ejecutar los scripts." (aviso informativo; NO bloquea nada — HITL, decide el humano).
- **Integración condicional con el 157 (regla literal):** si el archivo
  `frontend/src/components/dbcompare/MigrationPanel.tsx` EXISTE en el árbol al implementar,
  agregar también `<GatesPanel>` dentro de ese panel (mismo componente, misma prop `runId`); si
  NO existe, montar SOLO en `DbComparePage.tsx`. No crear dependencia de import incondicional.
- Gate por `health.gates_enabled`; OFF ⇒ no se renderiza nada.

**Test PRIMERO (TDD, vitest):**
`frontend/src/components/dbcompare/__tests__/gatesLogic.test.ts` — `statusFor` sin resultados ⇒
`sin_verificar`; `overallStatus` con mezcla pass/fail ⇒ `hay_fail`; lista vacía ⇒ `sin_gates`;
labels literales.
Comando:
```
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/__tests__/gatesLogic.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** vitest verde + `tsc --noEmit` 0.
**Flag:** `STACKY_DB_COMPARE_GATES_ENABLED` vía `health.gates_enabled`.
**Impacto por runtime:** idéntico. Fallback: flag OFF ⇒ UI idéntica a `main`.
**Trabajo del operador:** ninguno.

---

### F6 — Tablas de parámetro persistentes + claves naturales (backend + UI)

**Objetivo (1 frase):** el operador marca (una sola vez) qué tablas son "de parámetro" y define
claves naturales para tablas sin PK; el picker de datos las preselecciona y las tablas sin PK se
vuelven comparables.
**Valor:** salda el diferido explícito del 126 §6 y habilita el caso real `RCONTROLES` del prior
art; elimina la re-selección manual de ≤20 tablas en cada corrida
(`DataParitySection.tsx:121-145`).

**Archivo a crear:** `backend/services/dbcompare_table_prefs.py`
**Archivos a editar:** `backend/api/db_compare.py`, `backend/services/dbcompare_data.py`,
`frontend/src/components/dbcompare/DataParitySection.tsx`,
`frontend/src/components/dbcompare/tablePrefsLogic.ts` (crear),
`frontend/src/api/endpoints.ts`, `frontend/src/components/dbcompare/dbcompare.module.css`.

**Contrato TablePrefs v1 (NUEVO — archivo `data_dir()/db_compare/table_prefs.json`, GLOBAL como el
prior art `FallbackKeyColumns`; mono-operador, mismo producto RS en todos los ambientes):**
```json
{
  "version": 1,
  "tables": {
    "<schema>.<table>": {"natural_key": ["COL1", "COL2"], "param_table": true, "updated_at": "ISO"}
  }
}
```
- `natural_key`: lista no vacía de strings o `null`. Validación literal por columna: regex
  `^[A-Za-z0-9_$#]{1,128}$` (si falla, `ValueError`). El quoting al emitir SQL sigue siendo de
  `quote_ident` (no se guarda SQL, solo nombres).
- `param_table`: bool.

**Símbolos EXACTOS en `dbcompare_table_prefs.py`:**
- `PREFS_VERSION = 1`
- `def load_prefs() -> dict` — doc completo; sin archivo ⇒ `{"version": 1, "tables": {}}`.
- `def set_pref(schema: str, table: str, natural_key: list[str] | None = ..., param_table: bool | None = ...) -> dict`
  — actualización PARCIAL (parámetro no pasado = no tocar; `natural_key=None` explícito = borrar
  la clave). Escritura atómica. Devuelve el doc.
- `def natural_key_for(schema: str, table: str) -> list[str] | None`
- `def param_tables() -> list[str]` — lista de `"<schema>.<table>"` con `param_table` true,
  ordenada.

**Integración con datos (cambios ADITIVOS en `dbcompare_data.py`):**
- En la construcción de candidatas (consumida por `data_candidates_route`,
  `api/db_compare.py:372-373`): si la tabla NO tiene PK (hoy ⇒ `comparable: false`,
  `dbcompare_data.py:117`) y `STACKY_DB_COMPARE_TABLE_PREFS_ENABLED` ON y existe
  `natural_key_for(schema, table)`: validar que TODAS las columnas de la clave existan en las
  columnas de AMBOS snapshots; si sí ⇒ `comparable: true` + campos ADITIVOS
  `"key_source": "natural"` y `"key_cols": [...]`; si falta alguna columna ⇒ `comparable: false`
  + `"reason": "natural_key_invalid"`. Tablas con PK: `"key_source": "pk"` (aditivo). Toda
  candidata gana además `"param_table": true|false` (aditivo).
- En `diff_table_data` (`dbcompare_data.py:87`): aceptar parámetro keyword-only ADITIVO
  `key_cols: list[str] | None = None`; cuando viene, usar esas columnas como clave en lugar de la
  PK (el DataDiff v1 resultante lleva esas columnas en `pk_cols` — el campo congelado conserva
  su semántica "columnas usadas como clave" — más el campo ADITIVO `"key_source": "natural"`).
  El SELECT sigue construyéndose con `build_select` (`:48`) y ejecutándose vía `fetch_rows`
  (`:67`, guard `validate_select_only` intacto).
- En `start_data_diff_route` (`api/db_compare.py:410-411`): para cada tabla pedida sin PK, resolver
  `key_cols` desde prefs (flag ON); si la tabla no tiene ni PK ni clave natural válida ⇒ se
  mantiene el rechazo actual (sin cambios de contrato).

**Endpoints (gate `_require_enabled()` + `_require_table_prefs_enabled()` → 403 si flag OFF):**
- `GET /table-prefs` → `get_table_prefs_route()` — doc TablePrefs v1.
- `PUT /table-prefs` → `put_table_prefs_route()` — body
  `{"schema": str, "table": str, "natural_key": [...] | null, "param_table": bool}` (los dos
  últimos opcionales); 400 con `{"error": "natural_key_invalida"}` si la validación falla.

**UI (`DataParitySection.tsx` + `tablePrefsLogic.ts`):**
- Cada fila del picker gana: (a) toggle estrella "parámetro" (PUT `param_table`); (b) SOLO si la
  candidata viene `comparable:false` sin `natural_key`: botón "Definir clave…" que muestra un
  input inline (texto separado por comas) + Guardar (PUT `natural_key`).
- Preselección: al cargar candidatas con flag ON, las tablas `param_table:true` y `comparable:true`
  arrancan tildadas (cap 20 — el cap existente `_MAX_TABLES_PER_DATA_DIFF`,
  `dbcompare_data.py:25`, no se toca; si hay más de 20 param tables, se tildan las primeras 20 en
  orden alfabético).
- Lógica pura en `tablePrefsLogic.ts` (símbolos EXACTOS):
  `export function preselect(candidates: Candidate[], cap: number): string[]`;
  `export function parseNaturalKeyInput(raw: string): string[] | null` (split por coma, trim,
  vacíos fuera; null si no queda ninguna);
  `export function canDefineKey(candidate: Candidate): boolean`.

**Test PRIMERO (TDD):**
`backend/tests/test_plan176_dbcompare_table_prefs.py` — load vacío; set parcial; natural_key
inválida lanza; roundtrip atómico; `param_tables` ordenada.
`backend/tests/test_plan176_dbcompare_table_prefs_api.py` — 403 flag OFF; PUT/GET roundtrip; 400
clave inválida.
`backend/tests/test_plan176_dbcompare_natural_key_datadiff.py` — con sqlite `test-*`: tabla SIN PK
+ clave natural definida ⇒ candidata `comparable:true` con `key_source:"natural"` y
`diff_table_data` con `key_cols` produce DataDiff correcto (fixture con 1 fila only_source);
clave con columna inexistente ⇒ `reason:"natural_key_invalid"`; flag OFF ⇒ respuesta de
candidatas EXACTAMENTE como `main` (sin keys aditivas de prefs). **Bloqueante (KPI-3 y KPI-5).**
`frontend/src/components/dbcompare/__tests__/tablePrefsLogic.test.ts` — preselect respeta cap y
orden; parseNaturalKeyInput con espacios/vacíos; canDefineKey.
Comandos: pytest por archivo como en F1; vitest del archivo + `tsc --noEmit`.
**Criterio BINARIO:** los 4 archivos verdes.
**Flag:** `STACKY_DB_COMPARE_TABLE_PREFS_ENABLED`.
**Impacto por runtime:** idéntico. Fallback: flag OFF ⇒ candidatas y picker como `main`.
**Trabajo del operador:** ninguno obligatorio (marcar tablas/claves es opcional y se hace UNA vez).

---

### F7 — Verificación de cierre de migración (re-compare con expectativas)

**Objetivo (1 frase):** un botón "Verificar migración" que re-compara el par y evalúa expectativas
derivadas del triage: `confirmado` ⇒ ya no difiere; `excluido` ⇒ sigue difiriendo.
**Valor:** porta el paso 5 del replay de Pacífico (re-verificación con aserciones de residual,
`Invoke-DevTestParityReplay.ps1:736-758`): el operador sabe con evidencia si la migración quedó
completa y si NO tocó lo que no debía.

**Archivo a crear:** `backend/services/dbcompare_closure.py`
**Archivos a editar:** `backend/api/db_compare.py`,
`frontend/src/components/dbcompare/ClosurePanel.tsx` (crear),
`frontend/src/components/dbcompare/closureLogic.ts` (crear),
`frontend/src/components/dbcompare/DbComparePage.tsx`, `frontend/src/api/endpoints.ts`,
`frontend/src/components/dbcompare/dbcompare.module.css`.

**Contrato ClosureReport v1 (NUEVO, calculado on-demand, linkage persistido en
`data_dir()/db_compare/closure/<old_run_id>.json` = `{"version": 1, "old_run_id": ...,
"verification_run_id": ..., "created_at": "ISO"}`):**
```json
{
  "version": 1,
  "old_run_id": "...", "verification_run_id": "...",
  "results": [
    {"item_key": "...", "expectation": "resuelto|persiste", "status": "ok|violado"}
  ],
  "summary": {"ok": 0, "violado": 0, "sin_expectativa": 0}
}
```

**Símbolos EXACTOS en `dbcompare_closure.py`:**
- `CLOSURE_VERSION = 1`
- `def derive_expectations(old_diff: dict, triage: dict) -> list[dict]` — pura: por cada ítem del
  `old_diff["items"]`, decisión `confirmado` ⇒ `{"item_key", "expectation": "resuelto"}`;
  `excluido` ⇒ `{"item_key", "expectation": "persiste"}`; `pendiente` ⇒ sin expectativa (cuenta
  en `sin_expectativa`).
- `def evaluate_closure(old_run: dict, new_run: dict, triage: dict) -> dict` — pura: keys del
  nuevo diff = `{item_key_for_schema_item(i) for i in new_run["diff"]["items"]}`; `resuelto` ⇒
  `ok` si la key NO está; `persiste` ⇒ `ok` si la key SÍ está; lo demás `violado`. Devuelve
  ClosureReport v1.
- `def start_closure(old_run_id: str) -> dict` — carga old_run (`ValueError` si no existe o no
  está `done`); lanza `create_run(source, target, mode="fresh")`
  (`services/dbcompare_runs.py:130`, mismo lock por par y 409-busy existentes); persiste el
  linkage atómico; devuelve `{"verification_run_id": ...}`.

**Endpoints (gate `_require_enabled()` + `_require_triage_enabled()` — el cierre pertenece a la
capacidad de triage, misma flag):**
- `POST /runs/<run_id>/verify-closure` → `verify_closure_route()`. 404 run inexistente; 409 run no
  `done`; 409 si el par está ocupado (propaga el `DbCompareBusyError` existente, patrón de
  `create_compare_run_route`, `api/db_compare.py:185-186`). Respuesta **202**
  `{"verification_run_id": ...}`.
- `GET /runs/<run_id>/closure` → `get_closure_route()`. 404 si nunca se lanzó verificación para
  ese run; si el run de verificación sigue `running` ⇒ 409 `{"error": "verificacion_en_curso",
  "verification_run_id": ...}`; si está `done` ⇒ ClosureReport v1 calculado on-demand.

**UI (`ClosurePanel.tsx` + `closureLogic.ts`):**
- En la vista de resultados de un run `done` con triage cargado y ≥1 decisión: botón "Verificar
  migración" (POST verify-closure) → muestra progreso reutilizando el polling existente
  (`useCompareRun`, ya usado por `RunProgress.tsx`) → al terminar, panel con el reporte: filas
  `item_key · expectativa · estado` (`ok` verde / `violado` rojo con token `--dbc-danger`), y
  resumen `N ok · N violados · N sin expectativa`.
- **Integración condicional con el 157:** misma regla literal que F5 — si `MigrationPanel.tsx`
  existe, montar también ahí; si no, solo en `DbComparePage.tsx`.
- Lógica pura en `closureLogic.ts` (símbolos EXACTOS):
  `export function canVerify(runStatus: string, summary: {confirmado: number; excluido: number} | null): boolean`
  (true solo si `runStatus === "done"` y hay ≥1 decisión);
  `export function closureSummaryLabel(report: ClosureReport): string` (formato literal
  `"<ok> ok · <violado> violados · <sin_expectativa> sin expectativa"`).
**Test PRIMERO (TDD):**
`backend/tests/test_plan176_dbcompare_closure.py` (puro) — confirmado resuelto ⇒ ok; confirmado
aún presente ⇒ violado; excluido persiste ⇒ ok; excluido desaparecido ⇒ violado; pendiente ⇒
sin_expectativa; summary correcto; determinismo (orden por `item_key`).
`backend/tests/test_plan176_dbcompare_closure_api.py` — 403 flag OFF; 404 sin verificación
lanzada; 409 en curso; flujo completo con ambientes sqlite `test-*` (comparar → decidir → mutar la
BD destino del fixture → verify-closure → closure `done` con `ok`/`violado` esperados).
`frontend/src/components/dbcompare/__tests__/closureLogic.test.ts` — `canVerify` (no done ⇒
false; done sin decisiones ⇒ false; done con 1 confirmado ⇒ true); label literal.
Comandos: pytest por archivo; vitest del archivo + `tsc --noEmit`.
**Criterio BINARIO:** los 3 archivos verdes.
**Flag:** `STACKY_DB_COMPARE_TRIAGE_ENABLED` (misma capacidad).
**Impacto por runtime:** idéntico. Fallback: flag OFF ⇒ endpoints 403, UI no renderiza.
**Trabajo del operador:** ninguno (verificar es opcional, 1 click).

---

### F8 — Potencia visual del diff (UX v2)

**Objetivo (1 frase):** multi-filtro de tipos, export CSV/JSON del diff filtrado, diff por líneas
en definiciones de vistas, comparación de snapshots históricos y errores visibles.
**Valor:** elimina las 5 fricciones medidas de la vista de resultados sin dependencias nuevas.

**Archivos a crear:**
- `frontend/src/components/dbcompare/lineDiff.ts`
- `frontend/src/components/dbcompare/diffExport.ts`
**Archivos a editar:**
- `frontend/src/components/dbcompare/FiltersBar.tsx` (multi-selección de tipos)
- `frontend/src/components/dbcompare/DbComparePage.tsx` (estado `objectTypes: string[]`; hoy
  fuerza un solo valor)
- `frontend/src/components/dbcompare/ObjectDrilldown.tsx` (vistas: diff por líneas en lugar de los
  dos `<pre>` de `:149-152`)
- `frontend/src/components/dbcompare/SummaryHero.tsx` (botones "CSV" y "JSON" junto a
  "Exportar .md" de `:121`)
- `frontend/src/components/dbcompare/CompareWizard.tsx` (tercer modo "Histórico" junto a los
  radios fresh/cached de `:138`)
- `frontend/src/components/dbcompare/DataParitySection.tsx` y
  `frontend/src/components/dbcompare/DbComparePage.tsx` (reemplazar los `.catch(() => ...)`
  silenciosos de `DbComparePage.tsx:50,55` y `DataParitySection.tsx:69` por estado de error +
  banner `errorBanner` existente)
- `backend/services/dbcompare_runs.py` + `backend/api/db_compare.py` (modo snapshot histórico)
- `frontend/src/api/endpoints.ts`

**Cambios exactos:**
1. **Multi-filtro:** en `FiltersBar.tsx`, reemplazar el `<select>` único (`:48`) por chips
   toggleables (uno por `object_type` presente en el diff). `filterLogic.ts` YA acepta
   `objectTypes: string[]`; el único cambio de página es dejar de forzar `[value]`
   (`DbComparePage.tsx`). Extender los tests existentes de `filterLogic` con 1 caso multi-tipo.
2. **Export CSV/JSON** (`diffExport.ts`, símbolos EXACTOS):
   - `export function toCsv(items: DiffItem[]): string` — columnas literales en este orden:
     `object_type,schema,name,action,severity,kinds` (kinds unidos por `|`). Quoting RFC 4180
     literal: todo campo que contenga `,`, `"` o salto de línea se envuelve en comillas dobles y
     las comillas internas se duplican. Separador de filas `\r\n`. Sin BOM.
   - `export function toJson(items: DiffItem[]): string` — `JSON.stringify(items, null, 2)`.
   - En `SummaryHero.tsx`: dos botones que descargan Blob client-side
     (`URL.createObjectURL`) con nombres `diff_<run_id>.csv` / `diff_<run_id>.json`, aplicados a
     los ítems ACTUALMENTE FILTRADOS (misma lista que ve el operador).
3. **Diff por líneas de vistas** (`lineDiff.ts`, símbolos EXACTOS):
   - `export type LineOp = {op: "equal" | "add" | "del"; text: string};`
   - `export function diffLines(a: string, b: string): LineOp[]` — LCS por programación dinámica
     sobre líneas (split por `\n`, sin normalizar espacios). **Cap literal:** si
     `a.split("\n").length > 3000` o ídem `b`, devolver `null` (el caller cae al render actual de
     dos `<pre>`). Sin dependencias nuevas.
   - En `ObjectDrilldown.tsx` (`:149-152`): si ambos lados tienen definición y `diffLines` no
     devuelve null, render unificado: líneas `add` con clase `lineAdd` (token `--dbc-added`),
     `del` con `lineDel` (token `--dbc-removed`), `equal` sin clase; contenedor con
     `overflow-x: auto` en el CSS module. Si un lado falta o hay cap ⇒ render actual sin cambios.
4. **Snapshots históricos:**
   - Backend: `create_run` (`services/dbcompare_runs.py:130`) acepta parámetros keyword-only
     ADITIVOS `source_snapshot_id: str | None = None`, `target_snapshot_id: str | None = None`.
     Cuando AMBOS vienen: no tomar snapshots nuevos; cargar con `load_snapshot`
     (`services/dbcompare_snapshot.py:261`); `ValueError` si alguno no existe, si su `alias` no
     coincide con el ambiente correspondiente, o si los engines difieren (el motor de diff ya
     lanza `DbCompareDiffError` si difieren, `dbcompare_diff.py:284`). Si viene UNO solo ⇒
     `ValueError`.
   - `create_compare_run_route` (`api/db_compare.py:185-186`): leer los 2 campos ADITIVOS del
     body y pasarlos; 400 en `ValueError` (comportamiento de error existente).
   - Frontend: en `CompareWizard.tsx`, tercer radio "Histórico"; al elegirlo, por cada ambiente un
     `<select>` de snapshots poblado con el endpoint existente
     `GET /environments/<alias>/snapshots` (`api/db_compare.py:162-163`), mostrando
     `taken_at` + `content_hash` corto (8 chars). El submit envía los dos snapshot_ids.
   - Gate: el modo "Histórico" solo se muestra si `health.diff_ux_v2_enabled`.
5. **Errores visibles:** los catch silenciosos citados pasan a setear un estado de error rendereado
   con el patrón `errorBanner` que la página ya usa; el texto incluye la operación fallida
   ("No se pudieron cargar los ambientes", "No se pudieron cargar las corridas", "No se pudo
   consultar el diff de datos"). Sin dependencias de toast.

**Test PRIMERO (TDD, vitest por archivo):**
- `frontend/src/components/dbcompare/__tests__/lineDiff.test.ts` — iguales ⇒ todo equal; una línea
  cambiada ⇒ del+add; inserción pura; borrado puro; cap > 3000 líneas ⇒ null.
- `frontend/src/components/dbcompare/__tests__/diffExport.test.ts` — CSV golden con campo con
  coma, campo con comilla (duplicada) y campo con salto de línea; orden de columnas literal;
  JSON parseable con mismos ítems.
- extensión de los tests existentes de `filterLogic` (1 caso multi-tipo).
**Test backend:** `backend/tests/test_plan176_dbcompare_snapshot_mode.py` — run con ambos
snapshot_ids usa los snapshots dados (no toma nuevos: monkeypatch de `take_snapshot` que lanza si
se invoca); un solo id ⇒ `ValueError`/400; id inexistente ⇒ 400; alias que no coincide ⇒ 400;
body sin los campos nuevos ⇒ comportamiento EXACTO de `main`. **Bloqueante (KPI-5).**
Comandos: vitest por archivo + `tsc --noEmit`; pytest del archivo backend.
**Criterio BINARIO:** los 3 archivos vitest + el pytest verdes; `tsc --noEmit` 0.
**Flag:** `STACKY_DB_COMPARE_DIFF_UX_V2_ENABLED` (gatea multi-filtro, export, line diff, modo
Histórico; los errores visibles del punto 5 NO van bajo flag: son corrección de bug de
observabilidad, comportamiento con flag OFF solo difiere en mostrar un error real en vez de
tragarlo).
**Impacto por runtime:** idéntico. Fallback: flag OFF ⇒ UI como `main`.
**Trabajo del operador:** ninguno.

---

### F9 — Integración, ratchet, smoke y Definición de Hecho

**Objetivo (1 frase):** verificar el flujo end-to-end, dejar toda la regresión en el arnés y
documentar el smoke manual.
**Archivos a editar:** `backend/scripts/run_harness_tests.sh` + `.ps1` (confirmar los 10 archivos
`test_plan176_*.py` en `HARNESS_TEST_FILES`).
**Pasos:**
1. Backend: correr los 10 archivos de test del plan POR ARCHIVO con el venv real; pegar el output.
2. Frontend: `npx vitest run` de los 6 archivos nuevos/extendidos POR ARCHIVO +
   `npx tsc --noEmit`.
3. `test_harness_ratchet_meta.py` verde.
4. Smoke manual (checklist para el operador, HITL, no bloquea merge): con las 4 flags ON, sobre
   ambientes `test-` sqlite: (i) correr un compare, excluir 1 ítem con nota, regenerar scripts y
   verificar que el bundle no lo contiene y que `TRIAGE_EXCLUSIONS.md` sí; (ii) "Verificar
   precondiciones" sobre un diff con NOT NULL pinta fail con NULLs sembrados; (iii) marcar una
   tabla de parámetro, recargar candidatas y verla preseleccionada; definir clave natural en una
   tabla sin PK y compararla; (iv) "Verificar migración" muestra ok/violado coherentes; (v) export
   CSV/JSON descargan lo filtrado; modo Histórico compara 2 snapshots viejos. Con las 4 flags
   OFF: la página y la API son idénticas a `main`.
**Criterio BINARIO:** pasos 1-3 con exit 0 y outputs pegados en el PR; paso 4 documentado con su
resultado.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| 1 | Ejecutar SQL contra la BD del operador (gates) | Solo SELECT; guard `validate_select_only` OBLIGATORIO por gate (test bloqueante); solo por click explícito; cap `_MAX_GATES_PER_EVAL=50`; timeout existente; engine read-only pool 1. |
| 2 | Drift de nombres de kind entre `_GATE_RULES` y la tabla congelada del 123 | Test anti-drift bloqueante `test_gate_kinds_existen_en_kind_severity` (compara contra el `_KIND_SEVERITY` real importado). |
| 3 | Romper Manifest v1 / REGLA DE ORO al filtrar por triage | El filtrado ocurre ANTES de emitir; el assert del invariante (`dbcompare_scripts.py:896`) corre sobre piezas filtradas; `TRIAGE_EXCLUSIONS.md` va fuera de `entries`; test `test_regla_de_oro_se_mantiene_con_exclusiones`. |
| 4 | Triage aplicado "en silencio" sorprende al operador | Respuesta de generación con `triage_applied.excluded_count`; `TRIAGE_EXCLUSIONS.md` dentro del bundle y servible por el visor; sin decisiones ⇒ bundle idéntico (test bloqueante). |
| 5 | `item_key` inestable entre corridas rompería el cierre | La key NO incluye run_id/timestamps (solo object_type/schema/name); test de estabilidad + determinismo en F1/F7. |
| 6 | Clave natural mal definida produce diff de datos engañoso | Validación de existencia de columnas en AMBOS snapshots (`natural_key_invalid`); el operador la define explícitamente (HITL); mismo cap de filas existente. |
| 7 | Re-compare de cierre choca con corrida activa del par | Reusa el lock por par y el 409 `DbCompareBusyError` existentes (`dbcompare_runs.py:147`). |
| 8 | Campos aditivos rompen los tipos TS espejo | Los tipos espejo de 124 se extienden con campos OPCIONALES (`key_source?`, `param_table?`, `reason?`); `tsc --noEmit` en cada fase frontend. |
| 9 | PII en datos mostrados/exportados (diff de datos) | Preexistente de la serie (126) y ya anotado como riesgo #7 del Plan 157; este plan no agrega superficies nuevas de datos (el export CSV/JSON de F8 exporta el diff de ESQUEMA, no filas de datos). Sigue anotado para un plan futuro de masking. |
| 10 | Colisión con planes 172-175 (teclado/presets/virtualización/peek, sesión paralela) | Sin solapamiento de archivos objetivo: este plan no toca registro de atajos ni presets globales ni virtualización (declarada fuera de scope acá justamente porque el 174 la cubre a nivel app). |

## 6. Fuera de scope

- **Ejecutar scripts de migración (escritura) contra una BD** — doctrina de la serie 122-126:
  Stacky genera, el operador ejecuta. Las gates son la ÚNICA ejecución nueva y son SELECT puros.
- **Mapeo de diffs a scripts ticketeados existentes** (`trunk/BD`, prior art #5) — alto valor pero
  requiere integración con el repo del producto del operador; candidato a plan futuro.
- **Virtualización de listas largas** (`DiffList.tsx`) — la cubre a nivel aplicación el Plan 174
  (sesión paralela); duplicarla aquí sería colisión.
- **Scheduling / diffs programados / notificaciones** — siguen diferidos (123 §6, 124 §6).
- **Comparar 3+ ambientes a la vez** — sigue diferido (124 §6).
- **MERGE statements** en scripts de datos — sigue diferido (126 §6).
- **Snapshot v2 con precision/scale/max_length como subcampos** (prior art #6) — requiere versionar
  el contrato congelado Snapshot v1; se anota para una eventual serie v2 del comparador.
- **Masking de PII** en grids/exports de datos — se mantiene anotado (riesgo #9), igual que en el
  157.

## 7. Glosario + Orden de implementación + DoD

**Glosario (términos que un modelo menor podría no conocer):**
- **Triage:** decisión humana por ítem del diff: `confirmado` (migrarlo), `excluido` (no migrarlo,
  con nota del porqué), `pendiente` (aún sin decidir; se comporta como hoy).
- **Gate (de precondición):** consulta SELECT de solo lectura que verifica que un cambio riesgoso
  sea seguro ANTES de ejecutar el script (ej.: contar NULLs antes de un `ALTER ... NOT NULL`).
- **Clave natural:** conjunto de columnas elegido por el operador que identifica filas en una tabla
  SIN primary key formal (ej. `RCONTROLES` del producto RS).
- **Tabla de parámetro:** tabla de configuración del producto RS cuyos DATOS deben mantenerse en
  paridad entre ambientes (ej. `RCONTROLES`, `RMODULOS`, `RIDIOMA`).
- **Cierre de migración:** re-comparación posterior a que el operador ejecutó los scripts, con
  expectativas: lo confirmado debe haberse resuelto; lo excluido debe seguir difiriendo (prueba
  de que no se tocó).
- **Bundle:** directorio de scripts SQL generado por el Plan 125 (`01_backups/`, `02_paridad/`,
  `03_datos/`, `09_destructivo/`) con manifest y zip descargable.
- **REGLA DE ORO:** todo script que modifica/pisa una tabla tiene su resguardo pareado 1:1
  (invariante testeada del 125).
- **`validate_select_only`:** guard existente (`services/db_query.py`) que rechaza cualquier SQL
  que no sea SELECT; único camino permitido de ejecución contra una BD.
- **Master flag:** `STACKY_DB_COMPARE_ENABLED` (ya ON); las 4 flags nuevas cuelgan de ella vía
  `requires`.
- **Ratchet de tests:** lista `HARNESS_TEST_FILES` (solo crece) en `run_harness_tests.sh` +
  espejo `.ps1`; todo test backend nuevo debe registrarse ahí.

**Orden de implementación (numerado, por dependencia):**
1. F0 (flags + health + registro ratchet).
2. F1 (triage backend).
3. F2 (triage UI).
4. F3 (bundle respeta triage).
5. F4 (gates backend).
6. F5 (gates UI).
7. F6 (tablas de parámetro + claves naturales).
8. F7 (verificación de cierre).
9. F8 (potencia visual del diff).
10. F9 (integración + smoke + DoD).
(F4-F5, F6 y F8 son paralelizables entre sí una vez cerrada F1; F3 requiere F1; F7 requiere F1.)

**Definición de Hecho (DoD) global:**
- Las 4 flags existen, default ON, categorizadas en `comparador_bd`, aristas en
  `_REQUIRES_MAP_FROZEN`; `test_requires_map_is_frozen` y
  `test_every_registry_flag_is_categorized` verdes; `/health` las reporta.
- Triage v1 operativo: decidir por ítem con nota desde lista y drill-down; resumen en el hero;
  `exclusions.md` descargable.
- Bundle curado: ítems/filas excluidos no emiten scripts; `TRIAGE_EXCLUSIONS.md` en bundle y zip;
  REGLA DE ORO intacta; sin decisiones ⇒ bundle idéntico a `main`.
- Gates v1: derivación determinista desde la tabla cerrada `_GATE_RULES` (anti-drift verde);
  evaluación SOLO por click, cada SELECT por `validate_select_only`; export.sql descargable;
  panel con semáforo.
- TablePrefs v1: tablas de parámetro preseleccionadas; tabla sin PK con clave natural válida
  comparable en datos (`key_source:"natural"`); validación `natural_key_invalid`.
- ClosureReport v1: verificación de cierre con `ok`/`violado` por expectativa y resumen.
- UX v2: multi-filtro de tipos, export CSV/JSON del diff filtrado, diff por líneas en vistas (cap
  3000), modo Histórico de snapshots, errores de fetch visibles.
- Con las 4 flags OFF: API y UI idénticas a `main` (tests por fase verdes).
- Los 10 `test_plan176_*.py` en `HARNESS_TEST_FILES`; `test_harness_ratchet_meta.py` verde;
  `tsc --noEmit` 0; vitest de los 6 archivos frontend verde POR ARCHIVO.
- Ningún contrato congelado (Snapshot v1, SchemaDiff v1, Manifest v1, DataDiff v1) modificado;
  solo contratos nuevos versionados y campos aditivos opcionales.
