# Plan 181 — Masking determinista de secretos/PII en el data-diff: presentación protegida por default, scripts intactos, overrides HITL por columna

**Estado:** PROPUESTO (v1, 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`).

**Serie:** Comparador de BD — capa 6 (seguridad de presentación del data-diff). Prerequisito declarado del futuro "vigía de DATOS" (el 178 §7 lo excluyó por PII: "si algún día se considera, requiere su propio plan con masking" — este plan ES ese masking). Relación con 157/176/178/179/180: §2bis, con los DOS hunks quirúrgicos compartidos con el 176 declarados con guía de merge.

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Que los VALORES de columnas sensibles (passwords, tokens, connection strings) que el data-diff del 126 trae de las tablas comparadas lleguen ENMASCARADOS por default a toda superficie de presentación (respuesta API del run → grid de la UI), sin tocar jamás el motor ni los scripts DML del bundle — y que revelar una columna sea UNA decisión humana de 1 click, persistida.

### 1.2 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | Con la flag ON, un run cuyo data-diff contiene la columna `PASSWORD` sirve por `GET /api/db-compare/runs/<id>` esa columna enmascarada en TODAS sus apariciones (filas de `only_source`, `only_target`, `changed[].cells` y `changed[].pk`), y la tabla trae el campo aditivo `masked_columns` con `["PASSWORD"]`. | `tests/test_plan181_response.py::test_password_enmascarada_en_respuesta` |
| KPI-2 | Con `STACKY_DB_COMPARE_MASKING_ENABLED=false`, la respuesta de `GET /runs/<id>` es BYTE-idéntica a main (mismo `json.dumps` del mismo dict, sin copia ni campo aditivo), para el mismo run sembrado con datos sensibles. | `tests/test_plan181_response.py::test_off_byte_identico` |
| KPI-3 | Un override `visible` por columna (PUT prefs) hace que el próximo GET del run sirva esa columna en crudo, y el override SOBREVIVE un reinicio: las prefs viven SOLO en disco (`masking_prefs.json`) y se releen en cada aplicación — cero estado en memoria. | `tests/test_plan181_prefs.py::test_override_visible_persiste_y_releen_disco` |
| KPI-4 | **BLOQUEANTE — scripts intactos:** con masking ON y la columna `PASSWORD` enmascarada en la respuesta API, el bundle DML generado (`POST /runs/<id>/scripts`) es BYTE-idéntico al generado con masking OFF: los INSERT/UPDATE/DELETE llevan los valores REALES. | `tests/test_plan181_response.py::test_bundle_dml_byte_identico_con_masking_on` |
| KPI-5 | Detectores golden: por NOMBRE, `PASSWORD`, `Contrasena`, `API_KEY`, `CADENA_CONEXION`, `ClaveSecreta` ⇒ masked y `CLAVE`, `DESCRIPCION`, `EMAIL`, `VALOR` ⇒ visible; por VALOR (solo si el nombre no decidió), `eyJhbGciOiJIUzI1NiJ9.x` ⇒ masked, `Server=x;Password=y;` ⇒ masked, `hola` y `12345678` ⇒ visible. | `tests/test_plan181_masking_core.py` |
| KPI-6 | `apply_masking` NO muta su entrada: tras aplicarlo, el dict original del run/data-diff es estructuralmente idéntico a su copia previa. | `tests/test_plan181_masking_core.py::test_apply_no_muta_original` |
| KPI-7 | La suite dbcompare preexistente afectable (`test_plan122_dbcompare_api.py`, `test_plan123_dbcompare_api.py`, `test_plan123_dbcompare_runs.py`, `test_plan126_dbcompare_data_api.py`, `test_plan126_dbcompare_data_diff.py`, `test_plan126_dbcompare_data_scripts.py`) queda verde POR ARCHIVO sin editar ninguno. | comandos de F6 |

---

## 2. Por qué ahora / gap

1. **El diferido está anotado TRES veces en la serie**: 157 riesgo #7, 176 riesgo #9 ("se mantiene anotado... plan futuro de masking") y 178 §7 ("Vigía de DATOS: excluido por PII y costo; si algún día se considera, requiere su propio plan con masking"). Nadie lo tomó; este plan lo cierra.
2. **El riesgo es real y verificado**: el data-diff del 126 trae VALORES CRUDOS de las tablas comparadas — `diff_table_data` normaliza y devuelve `only_source`/`only_target` como dicts fila columna→valor y `changed[].cells` con `source`/`target` (`services/dbcompare_data.py:177-188`) — y `get_run_route` sirve el run entero con `jsonify(run)` sin ninguna transformación (`api/db_compare.py:222-230`). Una tabla de parámetros RS con una columna de contraseña de servicio o una cadena de conexión viaja hoy en claro a la UI.
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
| 176 (triage/gates/cierre) | `api/db_compare.py`, servicios nuevos, `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts`, `DataParitySection.tsx` (+ `tablePrefsLogic.ts`) | `api/db_compare.py` (1 hunk) + `DataParitySection.tsx` (2 hunks) + `endpoints.ts` (append) |
| 178 (radar/vigía) | `dbcompare_watch.py`/`dbcompare_baseline.py`/`api/db_compare_watch.py` (nuevos), `app.py`, `dbcompare_runs.py` (kwarg), `endpoints.ts`, `DbComparePage.tsx` | `endpoints.ts` (append; archivo compartido, zonas distintas) |
| 179 (snapshot v2) | `dbcompare_snapshot.py`, `dbcompare_diff.py`, registro de flags | NINGUNA |
| 180 (puente repo) | `dbcompare_repo_scripts.py`/`api/db_compare_repo.py` (nuevos), `DbComparePage.tsx`, `endpoints.ts` | `endpoints.ts` (append) |
| **181 (este)** | NUEVOS: `services/dbcompare_masking.py`, `api/db_compare_masking.py`, `DataMaskingBar.tsx`, `maskingLogic.ts`, `maskingLogic.test.ts`, 4 tests backend. EDITADOS: `api/db_compare.py` (SOLO `get_run_route`), `api/__init__.py` (2 líneas), `DataParitySection.tsx` (2 hunks), `endpoints.ts` (append), `dbcompare.module.css` (append), `harness_flags.py`, `config.py`, `test_harness_flags_requires.py`, runners | — |

**Guía de merge anti-176 (los 2 solapes reales, con zonas citadas):**

1. `api/db_compare.py` — este plan edita EXCLUSIVAMENTE el cuerpo de `get_run_route` (`:222-230`, 1 hunk de 2 líneas). Verificado que el doc del 176 NO menciona `get_run_route` (grep de `get_run_route` sobre `docs/176_*.md` → 0 hits; sus zonas declaradas en ese archivo son `start_data_diff_route`, `api/db_compare.py:410-411`, doc 176 `:675`, y rutas nuevas propias). Conflicto esperable: NINGUNO o adyacencia trivial; resolución: conservar ambos.
2. `DataParitySection.tsx` — este plan edita SOLO la zona del render del sub-estado `done` (`:152-155`: import arriba + 1 JSX junto a `<DataDiffTables/>` en `:154`). Las zonas que el 176 declara tocar en ese archivo son OTRAS: el catch silencioso `:69` (doc 176 `:80,:822-824`) y el picker `:121-145` (doc 176 `:627`). Sin solape de líneas; resolución ante adyacencia: conservar ambos.
3. `endpoints.ts` — append de un objeto NUEVO al final del archivo real (hoy 4228 líneas; verificar el final con `tail` al implementar). Gotcha conocido del repo (merge duplicado silencioso): tras cualquier merge, `npx tsc --noEmit` + `grep -c "export const DbCompareMasking" endpoints.ts` esperando exactamente 1.

**Nota de diseño sobre el hunk en `api/db_compare.py`** (por qué no cero, con alternativa descartada): `get_run_route:230` (`return jsonify(run)`) ES el único punto donde el data-diff sale hacia la UI — interceptarlo con `after_request` obligaría a re-parsear el JSON ya serializado de TODAS las respuestas del blueprint (frágil y caro); la edición quirúrgica de 2 líneas en el punto de serialización es estrictamente menor. El resto de la API nueva (prefs) va en blueprint propio `db_compare_masking` para NO engordar la colisión con el 176 (patrón ya establecido por 178/180).

---

## 3. Principios y guardarraíles

### 3.1 Doctrina presentación-vs-motor (literal)

El masking protege la PRESENTACIÓN, NUNCA el motor:

- El diff de datos compara valores REALES (`diff_table_data`, `services/dbcompare_data.py:87-211`) — enmascarar antes de comparar destruiría la detección. NO se toca.
- El run PERSISTE el data-diff crudo en disco (`run_data_diff` escribe "en el archivo del run", `services/dbcompare_data.py:215,219-239`) — límite v1 declarado (riesgo R3): disco local del operador mono-usuario, mismo perfil de riesgo que los snapshots ya persistidos por el 122.
- Los scripts DML del bundle (125/126) llevan valores REALES: son el artefacto de migración que el operador revisa y ejecuta; enmascararlos los rompería. El camino del bundle NO pasa por la respuesta HTTP: `generate_scripts_route` (`api/db_compare.py:260-277`) llama `generate_parity_bundle(run_id)` (`:274`) que RE-LEE el run desde disco por `run_id`, y `emit_data_scripts` consume ese data-diff persistido (`services/dbcompare_scripts.py:568-651`: lee `data_diff["only_source"]/["changed"]/["only_target"]` con los valores crudos). El masking vive SOLO en la serialización de `get_run_route` ⇒ los scripts quedan intactos POR CONSTRUCCIÓN (KPI-4 lo prueba byte a byte).
- Revelar una columna enmascarada = 1 click del operador (override persistido en MaskingPrefs v1). Seguridad por default SIN pérdida de capacidad.

### 3.2 HITL, contratos y rieles

- **HITL**: enmascarar es el default seguro; REVELAR es siempre decisión humana explícita y queda persistida (auditable en `masking_prefs.json` con `updated_at`). Ninguna acción automática nueva.
- **Contratos congelados intactos**: DataDiff v1 (`dbcompare_data.py:197-211`) NO cambia — el masking es una TRANSFORMACIÓN DE SALIDA sobre una copia; el campo `masked_columns` es aditivo y existe SOLO en la respuesta HTTP, jamás en disco. Snapshot v1, SchemaDiff v1 y Manifest v1: no se tocan.
- **Mono-operador sin auth real**: nada de RBAC; las prefs son un único archivo global.
- **3 runtimes**: feature de panel puro (Flask + React, sin LLM): idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro; fallback N/A.
- **No degradar**: con la flag OFF, respuesta byte-idéntica (KPI-2) y cero UI nueva; con ON, el costo de `apply_masking` está acotado por los caps ya existentes del 126: máx. 20 tablas por corrida (`_MAX_TABLES_PER_DATA_DIFF`, `dbcompare_data.py:25`) × máx. filas por lado `STACKY_DB_COMPARE_DATA_MAX_ROWS` (default 5000, `config.py:131-133`).
- **Flags por UI**: registro completo (§3.4); pytest por archivo con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`; tests registrados en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20` + espejo `.ps1`).
- **Frontend sin RTL/jsdom**: lógica en `.ts` puros con vitest; CERO `style={{...}}`; tokens `--dbc-*` existentes.

### 3.3 Detectores v1 (decisiones con evidencia)

- **Por NOMBRE — tupla cerrada de regex case-insensitive** (`re.search` sobre el nombre de columna): `password|passwd|pwd`, `secret`, `token`, `api[_-]?key`, `contrase`, `credencial`, `conn(ection)?[_-]?str(ing)?`, `cadena[_-]?conexion`, `clave[_-]?(secreta|privada|api|acceso)`.
  - **Decisión evidenciada — `clave` a secas EXCLUIDA**: en el dominio RS "clave" significa KEY de parámetro (`services/glossary.py:33`: "Tabla maestra de parámetros del sistema. Cada parámetro tiene clave + ..."); enmascarar `CLAVE` mataría la utilidad principal del data-diff (tablas de parámetros clave/valor). Solo se enmascaran los compuestos inequívocos (`clave_secreta`, `clave_api`, `clave_privada`, `clave_acceso`).
- **Por VALOR — segunda línea, SOLO si el nombre no matcheó**: JWT (`^eyJ[A-Za-z0-9_-]{10,}\.`) y connection string embebida (`(?i)(password|pwd)\s*=`). **Y NADA MÁS en v1** — límites declarados: NO Luhn (los IDs numéricos largos de tablas de parámetros darían falsos positivos), NO emails (en tablas de parámetro suelen ser configuración legítima que el operador necesita ver). Decisión explícita, revisable en un plan futuro.

### 3.4 Flag

`STACKY_DB_COMPARE_MASKING_ENABLED`, bool, **default ON**. Justificación literal: AUMENTA la seguridad por default sin quitar ninguna capacidad (revelar = 1 click persistido); no conecta a nada, no publica nada, no escribe fuera de `data_dir()`, no tiene prerequisitos ⇒ NINGUNA de las 4 excepciones duras aplica. Registro completo: `FLAG_REGISTRY` con alta en `_CURATED_DEFAULTS_ON` (`harness_flags.py:310`, única vía de default ON), `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`), `requires="STACKY_DB_COMPARE_ENABLED"` (plano, profundidad 1), arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`, junto a `:183-185`), default efectivo en `config.py` con el idioma literal de `:119-133`, y `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py` (PROHIBIDO a mano).

---

## 4. Contrato MaskingPrefs v1

Persistencia: `data_dir()/db_compare/masking_prefs.json` (escritura atómica tmp + `os.replace`, mismo espíritu que `_write_bundle_atomic`, `dbcompare_scripts.py:706-723`). Subdirectorio consistente con `db_compare/{snapshots,runs,bundles}`.

```json
{
  "version": 1,
  "overrides": {
    "dbo.RUSUARIOS.PASSWORD": {"state": "visible", "updated_at": "2026-07-18T15:00:00Z"},
    "dbo.RPARAM.VALOR": {"state": "masked", "updated_at": "2026-07-18T15:05:00Z"}
  }
}
```

- Clave: `"<schema>.<table>.<column>"` con los tres segmentos en el case EXACTO en que el DataDiff los trae (los nombres vienen del snapshot; el lookup usa la clave literal y, si no está, la variante UPPERCASE — regla cerrada de 2 intentos).
- `state`: `"visible"` (decisión humana de revelar — HITL) o `"masked"` (forzar aunque los detectores no lo atrapen). Un PUT con `state: "auto"` ELIMINA el override (vuelve a detección automática).
- Cero estado en memoria: las prefs se releen de disco en CADA aplicación (`load_prefs()` por request — el archivo es chico; esto garantiza KPI-3 sin caches ni invalidación).
- Archivo corrupto ⇒ `{}` (todo en automático), sin crash, log warning.

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

**Tests PRIMERO — `tests/test_plan181_api.py` (bloque flags):** `test_flag_registrada_bool_on_requires_master`, `test_flag_en_categoria`, `test_config_default_on`.
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
respuesta HTTP y nada más. Revelar = override HITL persistido (MaskingPrefs v1)."""
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

_VALUE_SAMPLE_ROWS = 50  # muestreo determinista por tabla y por lista (orden ya determinista por PK)


def column_name_is_sensitive(name: str) -> bool:
    return any(p.search(name or "") for p in _NAME_PATTERNS)


def value_is_sensitive(value) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(p.search(text) for p in _VALUE_PATTERNS)


def mask_value(value):
    """Regla EXACTA (golden): None -> None (la nulidad no es secreto y el grid
    distingue NULL); len(str)<=4 -> '••••'; si no -> '••••' + últimos 2 chars."""
    if value is None:
        return None
    text = str(value)
    if len(text) <= 4:
        return MASKED_PLACEHOLDER
    return MASKED_PLACEHOLDER + text[-2:]


def masking_plan(table_diff: dict, prefs: dict) -> dict[str, str]:
    """dict columna -> 'masked'|'visible' para UN DataDiff v1 de tabla
    (shape dbcompare_data.py:197-211). Precedencia: override prefs > nombre >
    valor > visible. PURA: no lee disco."""
    schema = table_diff.get("schema") or ""
    table = table_diff.get("table") or ""
    overrides = prefs.get("overrides") or {}
    plan: dict[str, str] = {}
    for col in table_diff.get("columns") or []:
        override = overrides.get(f"{schema}.{table}.{col}") or overrides.get(
            f"{schema}.{table}.{col}".upper()
        )
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
        key = f"{schema}.{table}.{col}"
        if key in overrides or key.upper() in overrides:
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
    NO muta el original (KPI-6). Agrega masked_columns (aditivo, SOLO respuesta)."""
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
- `test_mask_value_regla_exacta`: `None -> None`; `"abc" -> "••••"`; `"supersecret42" -> "••••42"`.
- `test_plan_precedencia_override_gana`: override `visible` sobre columna `PASSWORD` ⇒ visible; override `masked` sobre `DESCRIPCION` ⇒ masked; override `visible` NO es re-enmascarado por la segunda línea de valor.
- `test_plan_valor_solo_si_nombre_no_decidio`: columna `VALOR` con un JWT en la fila 1 ⇒ masked; el mismo JWT más allá de la fila 50 ⇒ visible (muestreo declarado y determinista).
- `test_apply_cuatro_apariciones` (KPI-1): fixture con la columna sensible presente en `only_source`, `only_target`, `changed.cells` y `changed.pk` ⇒ enmascarada en los 4 sitios; `masked_columns == ["PASSWORD"]`.
- `test_apply_no_muta_original` (KPI-6): deep-copy previa == original tras aplicar.
- `test_apply_sin_masked_no_copia_profunda`: con plan todo-visible, `out["only_source"] is table_diff["only_source"]` (misma referencia: cero costo).

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_masking_core.py -q`
**Criterio (binario):** 9 tests verdes; el módulo no importa nada de conexión ni de Flask.
**Flag:** sin efecto (sin llamadores). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — MaskingPrefs v1: store en disco (atómico, sin cache)

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
    """state: 'visible'|'masked' setea; 'auto' elimina el override. Retorna prefs."""
    if state not in ("visible", "masked", "auto"):
        raise ValueError(f"state inválido: {state!r} (visible|masked|auto)")
    key = f"{schema}.{table}.{column}"
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
- `test_set_visible_y_masked_persisten`.
- `test_auto_elimina_override`.
- `test_override_visible_persiste_y_releen_disco` (KPI-3): `set_override(...)`; simular "reinicio" escribiendo por fuera y llamando `load_prefs()` de nuevo ⇒ el override está; NO existe ninguna variable de módulo con las prefs cacheadas (assert por inspección: `load_prefs` devuelve objetos NUEVOS en cada llamada — `load_prefs() is not load_prefs()`).
- `test_state_invalido_lanza`.
- `test_archivo_corrupto_degrada_vacio`.
- `test_escritura_atomica_sin_tmp`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_prefs.py -q`
**Criterio (binario):** 7 tests verdes.
**Flag:** aún sin efecto en respuestas. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — Transformación de salida: `apply_to_run_response` + hunk quirúrgico en `get_run_route`

**Objetivo:** que la respuesta del run sirva el data-diff enmascarado con ON y sea byte-idéntica con OFF, sin tocar disco ni bundle.
**Valor:** el KPI central del plan queda operativo con 2 líneas en la API existente.

**Archivos a editar:**

1. `services/dbcompare_masking.py` — agregar:

```python
def masking_enabled() -> bool:
    import config as _config
    return bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)) and bool(
        getattr(_config.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False)
    )


def apply_to_run_response(run: dict) -> dict:
    """Punto ÚNICO de aplicación (doc 181 §3.1). Con flag OFF o sin data_diff:
    retorna EL MISMO objeto sin copia ni campo aditivo => jsonify byte-idéntico
    a main (KPI-2). Con ON: copia superficial del run + data_diff transformado."""
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

(el import puede ir arriba con los demás; el cuerpo del route no cambia en nada más. NINGUNA otra ruta se toca: `list_runs_route` sirve metadata sin `diff` ni `data_diff` — `dbcompare_runs.list_runs` excluye `diff` en `dbcompare_runs.py:227` y el data-diff solo viaja por `get_run_route`.)

**Tests PRIMERO — `tests/test_plan181_response.py`** (cliente Flask + run sembrado en `tmp_path` con `data_diff` que contiene columna `PASSWORD` con valores reales):
- `test_password_enmascarada_en_respuesta` (KPI-1): GET run con ON ⇒ los valores de `PASSWORD` en `only_source`/`only_target`/`changed.cells`/`changed.pk` respetan `mask_value` y `masked_columns == ["PASSWORD"]`.
- `test_off_byte_identico` (KPI-2): con la flag OFF (monkeypatch `config.config`), `resp.get_data()` es EXACTAMENTE igual al de main (comparar contra un GET con la función anulada: monkeypatch `apply_to_run_response` a identidad ⇒ mismos bytes; y además `masked_columns` ausente).
- `test_disco_retiene_crudo`: tras un GET con ON, releer el archivo del run en disco ⇒ los valores siguen CRUDOS (la transformación no toca persistencia).
- `test_bundle_dml_byte_identico_con_masking_on` (KPI-4, BLOQUEANTE): generar el bundle (`POST /runs/<id>/scripts`) con ON y con OFF sobre el mismo run sembrado ⇒ los archivos DML del bundle son byte-idénticos y contienen el valor REAL de `PASSWORD`.
- `test_tabla_con_error_pasa_tal_cual`: entrada de `tables` con `{"error": ...}` no se transforma ni rompe.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_response.py -q`
**Criterio (binario):** 5 tests verdes; `git diff` de `api/db_compare.py` muestra exactamente 1 hunk (más el import) y SOLO en `get_run_route`.
**Flag:** gate dentro de `masking_enabled()` (hot-apply por request). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — API de prefs: blueprint nuevo `db_compare_masking`

**Objetivo:** GET estado + PUT override por columna, en blueprint propio (cero engorde de `api/db_compare.py`).
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
| `PUT /masking/prefs` | `put_masking_override_route` | body `{"schema","table","column","state"}` con `state ∈ visible|masked|auto`; 400 con mensaje ante `ValueError` o campos vacíos; 200 `{"ok": true, "prefs": ...}` |

**Registro:** `api/__init__.py` — 2 líneas con el idioma de `:57` y `:118` (`from .db_compare_masking import bp as db_compare_masking_bp` + `api_bp.register_blueprint(db_compare_masking_bp)`).

**Tests PRIMERO — completar `tests/test_plan181_api.py`:**
- `test_403_master_off_y_masking_off`: ambas variantes ⇒ 403 en GET y PUT.
- `test_get_prefs_vacias`.
- `test_put_visible_y_get_refleja`.
- `test_put_auto_borra`.
- `test_put_state_invalido_400` y `test_put_campos_vacios_400`.
- `test_put_luego_get_run_revela` (integración con F3): sembrar run con `PASSWORD`, PUT `visible`, GET run ⇒ valores crudos y `masked_columns == []`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan181_api.py -q`
**Criterio (binario):** 7 tests de F4 (+3 de F0) verdes; `api/db_compare.py` sin cambios en esta fase.
**Flag:** doble gate 122+181. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F5 — Frontend: barra de masking con Revelar/Ocultar (2 hunks)

**Objetivo:** indicador de columnas enmascaradas + toggle por columna, con colisión mínima.
**Valor:** el HITL de revelar queda a 1 click, sin que el operador configure nada.

**Contexto verificado del grid:** los valores YA llegan enmascarados del backend (F3), así que el grid existente (`DataDiffTable`, `DataParitySection.tsx:178-216`) muestra `••••…` sin NINGÚN cambio. Lo único nuevo es la barra de control.

**Archivos a crear:**
1. `frontend/src/components/dbcompare/maskingLogic.ts` — puro:
   - Tipos locales: `MaskedTableInfo { key: string; schema: string; table: string; maskedColumns: string[] }` (los tipos de `dataDiffLogic.ts`/`dbcompareTypes.ts` NO se editan: el campo `masked_columns` se lee con un cast local — TS estructural ignora campos extra).
   - `collectMaskedTables(tables: Record<string, unknown>): MaskedTableInfo[]` — recorre `dataDiff.tables`, parsea la clave `"schema.tabla"` (mismo split que `parseCandidateKey` de `dataDiffLogic.ts`, redefinido local para no tocar ese archivo) y junta `masked_columns` no vacías, orden estable por key.
   - `toggleLabel(state: "masked" | "visible"): string` — "Revelar" / "Ocultar".
2. `frontend/src/components/dbcompare/DataMaskingBar.tsx` — autocontenido:
   - Props: `{ tables: Record<string, unknown>; onChanged: () => void }`.
   - `collectMaskedTables(tables)`; si vacío ⇒ `return null` (cero UI cuando no hay nada enmascarado, y cero UI con flag OFF porque el backend no manda `masked_columns`).
   - Render: banda compacta "Columnas protegidas" + por tabla, chips `schema.tabla.columna` con botón "Revelar" ⇒ `DbCompareMasking.putOverride({schema, table, column, state: "visible"})` + `onChanged()`; y un botón secundario "Ocultar de nuevo" (state `"auto"`) para volver al automático.
   - CERO `style={{...}}`; clases nuevas en `dbcompare.module.css` (append): `.maskingBar`, `.maskingChip`, `.maskingReveal`, con `var(--dbc-warn)` y `var(--dbc-unchanged)`.
3. `frontend/src/components/dbcompare/maskingLogic.test.ts` — vitest: `collectMaskedTables` (vacío ⇒ []; tablas con y sin `masked_columns`; parse de key con puntos solo en el primer separador), `toggleLabel`.

**Archivos a editar (mínimos):**
4. `frontend/src/api/endpoints.ts` — append AL FINAL REAL del archivo (verificar con `tail`; gotcha de merge §2bis):
   ```typescript
   // Plan 181 — Masking de secretos en el data-diff (prefs por columna).
   export const DbCompareMasking = {
     getPrefs: () => api.get<{ ok: boolean; prefs: MaskingPrefs }>("/api/db-compare/masking/prefs"),
     putOverride: (body: { schema: string; table: string; column: string; state: "visible" | "masked" | "auto" }) =>
       api.put<{ ok: boolean; prefs: MaskingPrefs }>("/api/db-compare/masking/prefs", body),
   };
   ```
   (tipo `MaskingPrefs` importado de `maskingLogic.ts`; si el helper `api` no tiene `put`, usar el idioma que el archivo ya use para PUT — verificar con grep `api.put` al implementar y, si no existe, `api.post` con method override NO: usar el verbo que exista; si solo hay get/post/delete, cambiar la ruta de F4 a POST — decisión a tomar CON el archivo a la vista, documentada en el PR).
5. `frontend/src/components/dbcompare/DataParitySection.tsx` — EXACTAMENTE 2 hunks en la zona `:152-155` (fuera de las zonas `:69` y `:121-145` que declara el 176 — §2bis):
   - 1 import: `import { DataMaskingBar } from "./DataMaskingBar";`
   - 1 JSX inmediatamente ANTES de la línea `{dataDiff && dataDiff.status === "done" && <DataDiffTables tables={dataDiff.tables} />}` (`:154`):
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
3. `"./venv/Scripts/python.exe" -m compileall services/dbcompare_masking.py api/db_compare_masking.py` limpio (gotcha PyInstaller collect-submodules).
4. Frontend: `npx tsc --noEmit` + vitest del archivo.
5. Smoke manual documentado en el PR (BD real): comparar datos de una tabla con columna de password real ⇒ grid muestra `••••…` + barra "Columnas protegidas"; click "Revelar" ⇒ valores crudos tras el refresh; `data\db_compare\masking_prefs.json` contiene el override; generar scripts ⇒ el DML del bundle lleva el valor real; apagar la flag por UI ⇒ todo en crudo sin barra.

**Criterio (binario):** puntos 1-4 verdes; punto 5 documentado.
**Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Falso positivo del detector oculta config legítima (p.ej. columna `TOKEN_TIMEOUT`) | El operador no ve un valor que necesita | Revelar = 1 click persistido (KPI-3); la tupla de nombres es cerrada y conservadora — `clave` a secas excluida con evidencia (`glossary.py:33`); el override queda en prefs para siempre |
| R2 | Falso negativo (secreto en columna de nombre neutro y valor no-JWT/no-connstring) | Secreto visible en UI | Límites v1 DECLARADOS (§3.3): segunda línea por valor cubre JWT/connstring; Luhn/emails son decisión explícita fuera de v1; el operador puede forzar `masked` por columna (PUT state=masked) — HITL en ambas direcciones |
| R3 | El run en disco retiene los valores crudos | Secretos en `data_dir()` local | Límite v1 declarado (§3.1): disco local del operador mono-usuario, MISMO perfil de riesgo que los snapshots ya persistidos (122) y que los bundles DML (125/126) que por doctrina llevan valores reales; masking de persistencia queda en §7 |
| R4 | Colisión de merge con el 176 en `api/db_compare.py` y `DataParitySection.tsx` | Conflictos o duplicado silencioso | Zonas citadas y disjuntas (§2bis: `get_run_route:222-230` — 0 menciones en doc 176; `DataParitySection:152-155` vs zonas 176 `:69`/`:121-145`); guía: conservar ambos + `tsc` + grep post-merge |
| R5 | Performance de `apply_masking` en tablas grandes | GET del run más lento | Acotado por caps EXISTENTES del 126: ≤20 tablas (`dbcompare_data.py:25`) × ≤`STACKY_DB_COMPARE_DATA_MAX_ROWS` filas por lado (default 5000, `config.py:131-133`); la copia profunda ocurre SOLO en tablas con columnas masked (F1: sin masked ⇒ misma referencia); muestreo de valor capado a 50 filas por lista |
| R6 | `masking_prefs.json` corrupto | Overrides perdidos temporalmente | Lectura defensiva ⇒ `{}` (vuelve a detección automática = default SEGURO: enmascara de más, nunca de menos), log warning, el próximo PUT lo regenera |
| R7 | Sesión paralela ocupa el número 181 antes del commit | Colisión de numeración (precedente: 171) | Número recalculado listando `docs/` inmediatamente antes del Write; si al commitear existe otro 181, renumerar ANTES de commitear |
| R8 | El placeholder `••••` (no-ASCII) rompe algún consumer | Render extraño | Los valores del DataDiff ya son strings normalizados arbitrarios (`sqlvalues.normalize_value`, `dbcompare_data.py:162`) y el grid los muestra tal cual (`DataParitySection.tsx:207-208`); el export md del run NO imprime filas de datos (verificado `export_markdown`, `dbcompare_runs.py:265-321`: solo esquema) |

---

## 7. Fuera de scope (diferidos explícitos de este plan)

- **Masking de la PERSISTENCIA** (cifrar/enmascarar el data-diff dentro del archivo del run): fuera de v1 — declarado como límite con perfil de riesgo aceptado (R3); si algún día se hace, es un plan propio con migración de runs.
- **Masking de los scripts DML del bundle**: NUNCA — por doctrina (§3.1): son el artefacto de migración; enmascararlos los rompería.
- **Vigía de DATOS** (re-comparación programada de datos): plan futuro que ESTE plan desbloquea (178 §7); no se implementa acá.
- **Detectores Luhn/tarjetas y emails**: decisión explícita v1 (§3.3) — falsos positivos inaceptables en tablas de parámetros; revisable en un plan futuro con evidencia.
- **Masking en el export markdown del run**: innecesario — el export NO imprime filas de datos (`dbcompare_runs.py:265-321`, verificado); si un export de datos aparece en el futuro, DEBE pasar por `apply_to_run_response` o equivalente (regla declarada para ese plan futuro).
- **RBAC / masking por usuario**: no aplica (mono-operador sin auth real).

---

## 8. Glosario, orden de implementación y DoD global

### Glosario

- **Masking de presentación**: transformación de la RESPUESTA HTTP del run (nunca del disco ni del motor) que reemplaza valores de columnas sensibles por `mask_value(...)`.
- **Detector por nombre / por valor**: primera y segunda línea de decisión automática (§3.3); el valor solo se consulta si el nombre no decidió y no hay override.
- **Override**: decisión humana persistida por columna (`visible` | `masked`); `auto` la elimina.
- **MaskingPrefs v1**: contrato del archivo de overrides (§4).
- **`masked_columns`**: campo ADITIVO por tabla que existe SOLO en la respuesta HTTP — la señal que la UI usa para la barra de control.
- **Doctrina presentación-vs-motor**: §3.1 — la regla que hace compatibles seguridad por default y scripts útiles.

### Orden de implementación (estricto)

F0 (flag) → F1 (núcleo puro) → F2 (prefs) → F3 (respuesta + hunk API) → F4 (API prefs) → F5 (frontend) → F6 (cierre). F2 depende solo de F0; F3 depende de F1+F2. Nada más es permutable.

### Definition of Done global

1. Los 7 KPIs de §1.2 verificados con sus tests/comandos (KPI-4 es BLOQUEANTE: sin bundle byte-idéntico no hay merge).
2. Los 4 `tests/test_plan181_*.py` verdes POR ARCHIVO y registrados en ambos runners.
3. Los 6 preexistentes del KPI-7 + `test_harness_flags*.py` verdes sin editar ninguno.
4. Frontend: vitest verde, `tsc --noEmit` limpio, 0 `style={{` en los `.tsx` nuevos.
5. `harness_defaults.env` regenerado por script (la flag nueva en `true`).
6. `git diff --stat` solo lista los archivos de la fila "181" de la tabla §2bis; en `api/db_compare.py` el único símbolo tocado es `get_run_route`.
7. Con la flag OFF: respuesta del run byte-idéntica a main, cero UI nueva, cero archivos nuevos leídos.
8. Smoke manual de F6 documentado en el PR.

---

**Changelog interno:** v1 (2026-07-18) — propuesta inicial.
Auto-consistencia KPI↔spec verificada: KPI-1↔`apply_masking` cubre las 4 apariciones incluyendo `changed[].pk` (F1) y el test lo exige; KPI-2↔`apply_to_run_response` hace early-return del MISMO objeto con flag OFF ANTES de cualquier copia (F3), por eso "byte-idéntico" es literal; KPI-3↔`load_prefs()` relee disco en cada aplicación y el contrato declara "cero estado en memoria" (F2/§4), por eso "sobrevive restart" no depende de ningún cache; KPI-4↔el bundle re-lee el run de disco (`api/db_compare.py:274` → `dbcompare_scripts.py:568`) y el masking vive solo en `get_run_route`, el test compara bundles ON vs OFF byte a byte; KPI-5↔la tupla de F1 contiene exactamente los patrones del KPI y excluye `clave` a secas (evidencia `glossary.py:33`); KPI-6↔`apply_masking` opera sobre `copy.deepcopy` cuando hay masked y el caso sin-masked devuelve referencias originales SOLO del subárbol no transformado (chequeado que no contradice KPI-6: sin masked no hay transformación alguna); R5↔el deep-copy ocurre solo con columnas masked y los caps citados (20 tablas / 5000 filas / muestreo 50) son los del código real (`dbcompare_data.py:25`, `config.py:131-133`).
