# Plan 180 — Puente diff→repo del producto: índice read-only de scripts SQL ticketeados y cobertura del diff

**Estado:** PROPUESTO (v1, 2026-07-18, autor Fable 5 vía `proponer-plan-stacky`).

**Serie:** Comparador de BD — capa 5 (puente al repo del producto del operador). Capas previas: 122-126 motor (IMPLEMENTADA en main), 157 config UX (papel), 176 triage/gates/cierre (papel), 178 radar/vigía (papel), 179 fidelidad snapshot v2 (papel). Relación con todas: tabla de intersección de archivos en §2bis — único solape real: 1 hunk en `DbComparePage.tsx` y el append final de `endpoints.ts` (compartidos con 176/178), con guía de merge declarada.

---

## 1. Título, objetivo y KPIs

### 1.1 Objetivo (1 frase)

Cuando el comparador muestra un diff, responder automáticamente — SOLO como información, jamás como acción — la pregunta que hoy el operador cruza a mano: "¿este cambio ya tiene script SQL ticketeado en el repo del producto?", mediante un índice local read-only de los `.sql` del workspace del proyecto activo (ruta relativa + ticket inferido + tablas afectadas) y un panel de cobertura por ítem del diff.

### 1.2 El prior art está EN el repo (evidencia)

- El diferido explícito: doc `176_PLAN_DB_COMPARE_TRIAGE_CURADO_GATES_READONLY_Y_VERIFICACION_DE_CIERRE.md:938` — "**Mapeo de diffs a scripts ticketeados existentes** (`trunk/BD`, prior art #5) — alto valor pero requiere integración con el repo del producto del operador; candidato a plan futuro". Este plan ES ese candidato.
- La convención real de nombres está citada dentro del propio backend: `services/glossary.py:25-26` da el ejemplo literal `trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql` — carpeta `trunk/BD/`, número de ticket AL INICIO del nombre de archivo, separado por ` - `. Las reglas de extracción de F1 salen de este ejemplo, no de una suposición.
- El workspace del producto ya está configurado por proyecto: `project_manager.py:12` muestra `"workspace_root": "C:/Repos/RSPacifico"` en el config de ejemplo, y `project_manager.py:291` comenta "raíz del repo (contiene trunk/)".

### 1.3 KPIs binarios

| KPI | Criterio binario | Cómo se verifica |
|---|---|---|
| KPI-1 | Con `STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED=false` (o master 122 OFF): todos los endpoints nuevos devuelven 403, cero UI nueva renderizada (el panel devuelve `null`), y la suite dbcompare preexistente queda verde sin editarla. | `tests/test_plan180_api.py::test_403_flags_off` + patrón health→null en F5 |
| KPI-2 | Sin workspace activo (`_active_workspace_root()` retorna `None`): `GET /repo-scripts` responde 200 `{"ok": true, "index": null, "workspace": null}` — no-op inocuo, sin error, sin traceback. | `tests/test_plan180_api.py::test_sin_workspace_noop` |
| KPI-3 | Índice determinista: dos escaneos del MISMO árbol de archivos producen `scripts` idénticos (lista, orden, tickets, tablas, hashes) — solo `generated_at` puede diferir. | `tests/test_plan180_scanner.py::test_indice_determinista` |
| KPI-4 | Extracción golden de tablas: un fixture `.sql` con `CREATE TABLE`, `ALTER TABLE`, `INSERT INTO`, `UPDATE ... SET`, `DELETE FROM` y `MERGE INTO` (con identificadores calificados, con brackets y con comillas) produce EXACTAMENTE el set esperado de tablas; y el nombre `600804 - Inserts RIDIOMA.sql` produce `ticket == "600804"`. | `tests/test_plan180_extract.py` |
| KPI-5 | Cobertura correcta: con un diff fixture de 3 ítems tabla (2 con script candidato, 1 sin) más 1 view y 1 sequence, `match_diff_items` devuelve `covered_count == 2` sobre los 3 ítems tabla, la view matchea por nombre igual que una tabla, la sequence devuelve candidatos `[]` por regla explícita, y los candidatos vienen rankeados por `mtime` descendente. | `tests/test_plan180_coverage.py` |
| KPI-6 | Cap de archivos respetado con truncation REPORTADA, no silenciosa: con `MAX_FILES=3` y 5 archivos `.sql` en el árbol, el índice tiene 3 scripts, `"truncated": true` y `"files_scanned": 3`. | `tests/test_plan180_scanner.py::test_cap_reportado` |
| KPI-7 | El escáner es read-only sobre el workspace: ningún archivo bajo el workspace se crea/modifica/borra durante el escaneo (la única escritura es `index.json` bajo `data_dir()`). | `tests/test_plan180_scanner.py::test_workspace_intacto` (snapshot de mtimes antes/después) |

---

## 2. Por qué ahora / gap

1. **El cruce manual es el eslabón más lento del ciclo real**: el operador del producto RS ya escribe scripts SQL ticketeados en el repo (`trunk/BD/...`, evidencia §1.2). Cuando el comparador reporta N diferencias, la pregunta operativa inmediata es "¿cuáles de estas YA tienen script en el repo y cuáles hay que escribir?". Hoy eso es abrir el explorador de archivos y buscar a ojo, ítem por ítem.
2. **El diferido está declarado dos veces**: prior art #5 del debate de la serie y 176 §6 textual (`docs/176_...md:938`). Nadie lo tomó: 178 fue radar (scheduling) y 179 fue fidelidad (motor). Este cierra el tercero.
3. **Es barato y de riesgo mínimo**: filesystem local read-only, sin conexiones a BD, sin credenciales nuevas, sin daemons nuevos (el 178 ya agrega el suyo; este plan NO crea threads), sin tocar ningún contrato congelado.
4. **Onboarding literalmente casi nulo**: el workspace ya está configurado por proyecto (`workspace_root`, `project_manager.py:12,155`); el glob default cubre la convención real del prior art; el panel aparece solo cuando hay diff activo e índice con datos — si no hay workspace o no hay `.sql`, no aparece nada y nada falla.
5. **Verificado que NO reinventa nada** (claims negativos con comando):
   - `grep -rn "repo_scripts" "Stacky Agents/backend/"` → **0 hits** (el nombre del índice está libre; nada parecido existe).
   - `grep -n "\.sql" "Stacky Agents/backend/services/"` (recursivo) → **16 hits en 13 archivos**, TODOS listados y clasificados: whitelists de extensiones para adjuntos/citas/salud documental (`ado_client.py:452`, `ado_context.py:85`, `doc_evidence.py:106`, `doc_graph.py:371`, `incident_store.py:29`, `jira_client.py:40`, `mantis_client.py:69`, `repo_explainer.py:27`), generadores de SQL del propio comparador que EMITEN archivos pero no escanean el workspace (`dbcompare_scripts.py:563,592,631`, `dbcompare_sqlnames.py:53`), un docstring con el ejemplo del prior art (`glossary.py:25-26`) y dos menciones no relacionadas (`live_db.py:46` clave de dict, `local_diagnostics.py:363` ruta de sqlite). **Ninguno construye un índice persistido de scripts SQL del workspace.**
   - `doc_indexer.py` solo indexa Markdown: `rglob("*.md")` en `:225,:270`, `glob("*.md")` en `:281`, `glob("*.agent.md")` en `:302` — no toca `.sql`.

---

## 2bis. Relación con 157 / 176 / 178 / 179 (tabla de intersección de archivos)

| Plan | Archivos que toca (según su doc) | Intersección con 180 |
|---|---|---|
| 157 (config UX) | `EnvSetupWizard.tsx`, `CredentialWarningBanner.tsx`, `dbcompare_config_import.py` (nuevo), `MigrationPanel.tsx` | NINGUNA |
| 176 (triage/gates/cierre) | `api/db_compare.py`, servicios nuevos de triage/gates/tableprefs/closure, `DbComparePage.tsx`, `SummaryHero.tsx`, `endpoints.ts` | `DbComparePage.tsx` (1 hunk) + `endpoints.ts` (append) |
| 178 (radar/vigía) | `services/dbcompare_watch.py` (nuevo), `services/dbcompare_baseline.py` (nuevo), `api/db_compare_watch.py` (nuevo), `app.py`, `services/dbcompare_runs.py` (kwarg aditivo), `endpoints.ts`, `DbComparePage.tsx` | `DbComparePage.tsx` (1 hunk) + `endpoints.ts` (append) |
| 179 (snapshot v2) | `services/dbcompare_snapshot.py`, `services/dbcompare_diff.py`, registro de flags | NINGUNA |
| **180 (este)** | NUEVOS: `services/dbcompare_repo_scripts.py`, `api/db_compare_repo.py`, `RepoCoveragePanel.tsx`, `repoCoverageLogic.ts`, `repoCoverageTypes.ts`, `repoCoverageLogic.test.ts`, 2 tests backend. EDITADOS: `api/__init__.py` (2 líneas), `DbComparePage.tsx` (1 import + 1 JSX), `endpoints.ts` (append final), `dbcompare.module.css` (append final), `harness_flags.py`, `config.py`, `test_harness_flags_requires.py`, runners sh/ps1 | — |

- **`api/db_compare.py` NO se toca** (lo toca el 176): blueprint NUEVO propio `db_compare_repo` registrado en `api/__init__.py`, patrón idéntico al que el 178 declaró (`api/__init__.py:57` import + `:118` `api_bp.register_blueprint(...)`). Flask admite dos blueprints con el MISMO `url_prefix="/db-compare"` y nombres distintos; las rutas nuevas (`/repo-scripts`, `/repo-scripts/refresh`, `/runs/<run_id>/repo-coverage`) NO existen en la tabla de rutas actual del blueprint `db_compare` (verificada completa: `api/db_compare.py:52-411` — las subrutas de `/runs/<run_id>/` existentes son `export.md`, `scripts`, `scripts/file`, `scripts.zip`, `data-candidates`, `data-diff`; `repo-coverage` está libre).
- **Guía de merge del hunk compartido** (`DbComparePage.tsx` y `endpoints.ts`, compartidos con 176/178 si se implementan en paralelo): cada plan agrega SU import y SU elemento JSX en posiciones distintas del mismo archivo; el conflicto esperable es de adyacencia trivial y la resolución es SIEMPRE conservar ambos lados. Además existe el gotcha documentado del repo: git puede fusionar sin marcar conflicto y duplicar una línea de cierre — tras CUALQUIER merge que toque estos archivos, correr `npx tsc --noEmit` y `grep -c "export const DbCompareRepo" endpoints.ts` esperando exactamente 1.
- **Integración con el triage del 176**: CONDICIONAL futura — si el 176 se implementa, su UI de triage PUEDE mostrar la cobertura como columna informativa consumiendo `GET /runs/<run_id>/repo-coverage`; nada de este plan depende de eso ni lo implementa.

---

## 3. Principios y guardarraíles

- **HITL absoluto — solo informa**: la cobertura es INFORMACIÓN. CERO exclusiones automáticas de ítems del diff, CERO ediciones de scripts, CERO ejecución de SQL, CERO creación de archivos en el workspace. La decisión ("este cambio ya está cubierto por el ticket X") sigue siendo del operador (o de su triage humano del 176 cuando exista).
- **Read-only sobre filesystem LOCAL**: el escáner solo hace `walk` + `read_text` bajo el `workspace_root` del proyecto activo. La única escritura del plan es `data_dir()/db_compare/repo_scripts/index.json` (patrón atómico tmp + `os.replace`, mismo espíritu que `_write_bundle_atomic`, `services/dbcompare_scripts.py:706-723`).
- **Sin daemons nuevos**: el 178 ya agrega un thread; este plan NO crea ninguno. El refresco es bajo demanda (POST explícito) más un auto-escaneo inline la primera vez (F2, decisión declarada con su justificación).
- **Contratos congelados intactos**: Snapshot v1 (122 §F3), SchemaDiff v1 (123 §F1), Manifest v1 (125 §F3), DataDiff v1 (126 §F1-F2) no se tocan. Este plan agrega UN contrato nuevo versionado: RepoScriptIndex v1 (§4). El diff se CONSUME (lectura de `run["diff"]["items"]` vía `get_run`, `services/dbcompare_runs.py:207-214`; shape de items en `services/dbcompare_diff.py:311-331`), jamás se modifica.
- **Mono-operador sin auth real**: nada de RBAC.
- **3 runtimes**: feature de PANEL (Flask + React, sin LLM): idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro; fallback N/A (no depende ni de drivers de BD: opera sobre archivos y sobre runs ya persistidos).
- **No degradar**: con flags OFF, API y UI idénticas a main (KPI-1); el escaneo está acotado por cap + lista de exclusión de directorios pesados (F2) para que un workspace gigante no cuelgue el request.
- **Flags por UI**: las 3 flags nuevas quedan visibles/editables en el panel del arnés, categoría `comparador_bd` (`services/harness_flags.py:106-108`, `_CATEGORY_KEYS` `:320-324`), con `env_only=False` implícito (default del registro) — regla dura operator-config-always-via-ui (precedente literal `harness_flags.py:2910`).
- **Tests por archivo** con `./venv/Scripts/python.exe` (fallback `./.venv/Scripts/python.exe`) desde `Stacky Agents/backend`; registro en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh:20` + espejo `run_harness_tests.ps1`).
- **Frontend sin RTL/jsdom** (gap estructural conocido): lógica en `.ts` puros con vitest por archivo + `npx tsc --noEmit`; CERO `style={{...}}` en `.tsx` nuevos (ratchet `uiDebtRatchet`); estilos en `dbcompare.module.css` con los tokens `--dbc-*` existentes.

### 3.1 Resolución del workspace (símbolos exactos, verificados)

- `runtime_paths._active_workspace_root() -> Path | None` (`runtime_paths.py:66-84`): lee el marcador `data_dir()/active_project.json` y cae al primer proyecto con `config.json` real si el marcador está vacío o huérfano (mismo fallback que `project_manager.get_active_project()`, documentado en el propio docstring `:79-84`). Retorna `None` si no hay ningún proyecto utilizable.
- Este plan usa ESA función como única fuente del workspace (importando el MÓDULO: `from runtime_paths import ...` no — `import runtime_paths` y llamar `runtime_paths._active_workspace_root()`, para que el monkeypatch de tests funcione igual que el precedente masivo de `tests/test_runtime_paths.py:36,78,87,98,109,122,129,148,171`, que la mockea exactamente así).
- Equivalente de más alto nivel disponible: `project_manager.get_active_project()` (`project_manager.py:65`) + `get_project_config(name)` (`:55`) con clave `"workspace_root"` — NO se usa para evitar duplicar la lógica de fallback que `_active_workspace_root()` ya encapsula.
- Si `_active_workspace_root()` retorna `None`: TODO el feature es no-op inocuo (KPI-2) — sin excepción, sin log de error (un `logger.info` como máximo).

### 3.2 Flags (mecanismo decidido con evidencia)

El registry de flags soporta los tipos `bool`, `int`, `float`, `csv`, `json` y `str` (inventario por `grep -o 'type="[a-z]+"' services/harness_flags.py`: 220+ specs; `str` real en `:1640,:2866,:2932,:2957,:2968,:3006,:3333,:3346`; `csv` real en `:2918` entre otros). Decisión:

1. `STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED` — `type="bool"`, `default=True` vía `_CURATED_DEFAULTS_ON` (`harness_flags.py:310`, única vía para default ON). **Justificación literal del default ON**: read-only sobre archivos LOCALES del workspace ya configurado, sin credenciales nuevas, sin conexiones de red ni de BD, sin acciones automáticas ⇒ NINGUNA de las 4 excepciones duras aplica; si no hay workspace activo o el glob no matchea nada, es no-op inocuo — esto ES el onboarding casi nulo.
2. `STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS` — `type="csv"` (los patrones son una LISTA separada por comas; `csv` es el idioma del registry para listas — precedente `STACKY_CODEBASE_MEMORY_MCP_PROJECTS`, `harness_flags.py:2916-2929`). SIN `default=` en el spec (gotcha documentado: `default_is_known()` trata cualquier `default` no-None como "curado" y ese set es solo para bools True — comentario literal en `harness_flags.py:3143-3147`); el valor efectivo vive en `config.py`: `"trunk/BD/**/*.sql,**/BD/**/*.sql"` (primer patrón = convención literal del prior art `glossary.py:25`; segundo = variante para repos donde `BD/` no cuelga de `trunk/`).
3. `STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES` — `type="int"`, SIN `default=`, `min_value=100`, `max_value=50000` (patrón bounds idéntico a `STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC`, `harness_flags.py:3137-3151`); valor efectivo en `config.py`: `5000`.

Las tres con `requires="STACKY_DB_COMPARE_ENABLED"` (plano, profundidad 1 — jamás encadenar a la flag hermana bool), categoría `comparador_bd`, aristas nuevas en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`, junto a `:183-185`), y `harness_defaults.env` regenerado por `scripts/export_harness_defaults.py` (PROHIBIDO a mano).

---

## 4. Contrato RepoScriptIndex v1

Persistencia: `data_dir()/db_compare/repo_scripts/index.json` (subdirectorio nuevo, consistente con los existentes `db_compare/snapshots` — `dbcompare_snapshot.py:30`, `db_compare/runs` — `dbcompare_runs.py:30`, `db_compare/bundles` — `dbcompare_scripts.py:660`).

```json
{
  "version": 1,
  "workspace_root": "C:/Repos/RSPacifico",
  "generated_at": "2026-07-18T15:00:00Z",
  "globs": ["trunk/BD/**/*.sql", "**/BD/**/*.sql"],
  "files_scanned": 812,
  "truncated": false,
  "scripts": [
    {
      "path": "trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql",
      "ticket": "600804",
      "tables": ["RIDIOMA"],
      "tables_qualified": ["DBO.RIDIOMA"],
      "mtime": 1720000000,
      "size_bytes": 1234,
      "sha256_12": "a1b2c3d4e5f6"
    }
  ]
}
```

Reglas del contrato:

- `path`: SIEMPRE relativa al `workspace_root`, con `/` como separador (normalizada con `.as_posix()`), ordenada alfabéticamente en la lista (determinismo, KPI-3).
- `ticket`: string de dígitos o `null` (regla de inferencia en F1).
- `tables`: últimos segmentos de identificador, UPPERCASE, dedup, orden alfabético. `tables_qualified`: formas `SCHEMA.TABLA` UPPERCASE solo cuando el script calificó el identificador; dedup, orden alfabético.
- `mtime`: entero (`int(st_mtime)`); `sha256_12`: primeros 12 hex del sha256 del CONTENIDO leído (misma lectura tolerante de F1).
- `truncated`: `true` sii el escaneo se detuvo por `MAX_FILES` — SIEMPRE reportado, nunca silencioso (KPI-6).
- Lectura defensiva: `index.json` corrupto o con `version` desconocida ⇒ se trata como inexistente (`null`) y el próximo GET/refresh lo regenera; jamás crashea un endpoint.
- Campos aditivos opcionales permitidos a futuro; los existentes no se reinterpretan.

---

## 5. Fases

Orden estricto: F0 → F1 → F2 → F3 → F4 → F5 → F6. Cada fase termina con sus tests verdes ANTES de la siguiente (TDD: tests primero, verlos fallar por la razón correcta, implementar, verlos pasar).

---

### F0 — Flags, config y aristas

**Objetivo:** registrar las 3 flags (§3.2) sin comportamiento nuevo.
**Valor:** kill-switch y parámetros visibles en el panel del arnés desde el día 0.

**Archivos a editar (exactos):**

1. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CURATED_DEFAULTS_ON` (`:310` zona): agregar `"STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED",  # Plan 180 — puente diff→repo (read-only local, ninguna excepción dura aplica)`.
   - `_CATEGORY_KEYS["comparador_bd"]` (`:320-324`): agregar las 3 keys con comentario `# Plan 180`.
   - `FLAG_REGISTRY`, después del bloque del plan 126 (`:3162-3175`) — y si el 178/179 ya insertaron los suyos ahí, después del último bloque `STACKY_DB_COMPARE_*` existente al momento de implementar:
     ```python
     # ── Plan 180 — Puente diff→repo: índice de scripts SQL ticketeados ──────
     FlagSpec(
         key="STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED",
         type="bool",
         default=True,  # read-only sobre archivos LOCALES del workspace ya configurado; sin credenciales, sin red, sin acciones automáticas => ninguna excepción dura aplica. Sin workspace o sin .sql => no-op inocuo.
         label="Comparador BD: puente al repo (scripts ticketeados)",
         description="Indexa (solo lectura) los scripts .sql ticketeados del workspace del proyecto activo y muestra qué ítems del diff ya tienen script candidato. Solo informa: nunca excluye, edita ni ejecuta nada.",
         group="global",
         requires="STACKY_DB_COMPARE_ENABLED",
     ),
     FlagSpec(
         key="STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS",
         type="csv",
         label="Comparador BD: patrones de scripts del repo (CSV)",
         description="Globs relativos al workspace_root del proyecto activo donde viven los .sql ticketeados. Default: trunk/BD/**/*.sql,**/BD/**/*.sql (convención del prior art).",
         group="global",
         # NO default= acá: mismo gotcha que STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
         # (harness_flags.py:3143-3147) — el valor real vive en config.py.
         requires="STACKY_DB_COMPARE_ENABLED",
     ),
     FlagSpec(
         key="STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES",
         type="int",
         label="Comparador BD: máx. archivos escaneados por refresh",
         description="Cap duro de archivos .sql procesados por escaneo del puente al repo; excedente = índice truncado REPORTADO. Default 5000.",
         group="global",
         # NO default= acá: mismo gotcha; el valor real "5000" vive en config.py.
         requires="STACKY_DB_COMPARE_ENABLED",
         min_value=100,
         max_value=50000,
     ),
     ```
2. `Stacky Agents/backend/config.py` — después del último bloque `STACKY_DB_COMPARE_*` (hoy `:127-133`), copiando el idioma literal de `:119-133`:
   ```python
   # ── Plan 180 — Puente diff→repo (índice read-only de scripts ticketeados) ──
   STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED: bool = os.getenv(
       "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED", "true"
   ).strip().lower() == "true"
   STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS: str = os.getenv(
       "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS", "trunk/BD/**/*.sql,**/BD/**/*.sql"
   ).strip()
   STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES: int = int(
       os.getenv("STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES", "5000")
   )
   ```
3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — `_REQUIRES_MAP_FROZEN` (`:120`, junto a `:183-185`): 3 aristas nuevas `"STACKY_DB_COMPARE_REPO_BRIDGE_*": "STACKY_DB_COMPARE_ENABLED",  # Plan 180` (una línea por key).
4. Runners: agregar `tests/test_plan180_extract.py`, `tests/test_plan180_scanner.py`, `tests/test_plan180_coverage.py`, `tests/test_plan180_api.py` a `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`) y al espejo `.ps1`.
5. Regenerar `harness_defaults.env`: `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" scripts/export_harness_defaults.py`.

**Tests PRIMERO — `tests/test_plan180_api.py` (primer bloque, solo flags):**
- `test_flags_registradas`: las 3 existen con tipos `bool`/`csv`/`int`, la bool con `default is True`, las otras dos con `default is None`, la int con bounds (100, 50000), las 3 con `requires == "STACKY_DB_COMPARE_ENABLED"`.
- `test_flags_en_categoria`: las 3 en `_CATEGORY_KEYS["comparador_bd"]`.
- `test_config_defaults`: `config.config.STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED is True`, `...GLOBS == "trunk/BD/**/*.sql,**/BD/**/*.sql"`, `...MAX_FILES == 5000` (env limpio).

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan180_api.py -q`
**También verdes:** `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`.
**Criterio (binario):** 3 tests nuevos + 2 preexistentes verdes; `harness_defaults.env` regenerado por script.
**Flag:** las propias (sin efecto aún). **Runtimes:** idéntico en los 3 (panel). **Trabajo del operador:** ninguno.

---

### F1 — Extracción pura: ticket y tablas (reglas literales)

**Objetivo:** funciones puras de parsing en el módulo nuevo, sin filesystem todavía.
**Valor:** el corazón determinista y golden-testeable del puente.

**Archivo a crear:** `Stacky Agents/backend/services/dbcompare_repo_scripts.py` con este encabezado y estas funciones:

```python
"""Plan 180 — Puente diff→repo: índice read-only de scripts SQL ticketeados.

HITL absoluto: este módulo SOLO informa. Nunca excluye ítems del diff, nunca
edita ni ejecuta scripts, nunca escribe bajo el workspace (única escritura:
data_dir()/db_compare/repo_scripts/index.json).

Convención del prior art (evidencia services/glossary.py:25):
    trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql
=> ticket = primer grupo de 4-7 dígitos al inicio del nombre (fallback: carpetas).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

import runtime_paths

INDEX_VERSION = 1
_INDEX_DIRNAME = "db_compare/repo_scripts"

_TICKET_RE = re.compile(r"^\s*(\d{4,7})\b")

# Regex de sentencias DML/DDL soportadas (case-insensitive, por línea).
# LÍMITES DECLARADOS (esto NO es un parser SQL): ver docstring de extract_tables.
_TABLE_PATTERNS = (
    re.compile(r"\b(?:CREATE|ALTER)\s+TABLE\s+([\[\]\"\w.]+)", re.IGNORECASE),
    re.compile(r"\bINSERT\s+INTO\s+([\[\]\"\w.]+)", re.IGNORECASE),
    re.compile(r"\bUPDATE\s+([\[\]\"\w.]+)\s+SET\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\s+([\[\]\"\w.]+)", re.IGNORECASE),
    re.compile(r"\bMERGE\s+INTO\s+([\[\]\"\w.]+)", re.IGNORECASE),
)


def infer_ticket(rel_path: str) -> str | None:
    """Regla literal: 1) nombre de archivo; 2) segmentos de carpeta del más
    profundo al más superficial. Primer match de _TICKET_RE gana. None si nada."""
    parts = PurePosixPath(rel_path).parts
    for segment in (parts[-1], *reversed(parts[:-1])):
        m = _TICKET_RE.match(segment)
        if m:
            return m.group(1)
    return None


def _clean_identifier(raw: str) -> tuple[str | None, str | None]:
    """'[dbo].[RIDIOMA]' -> ('RIDIOMA', 'DBO.RIDIOMA'); 'RIDIOMA' -> ('RIDIOMA', None).
    Identificadores que empiezan con '#' o '@' (temporales/variables) -> (None, None)."""
    cleaned = raw.replace("[", "").replace("]", "").replace('"', "").strip().rstrip(";,")
    if not cleaned or cleaned[0] in ("#", "@"):
        return None, None
    segments = [s for s in cleaned.split(".") if s]
    if not segments:
        return None, None
    table = segments[-1].upper()
    qualified = f"{segments[-2].upper()}.{table}" if len(segments) >= 2 else None
    return table, qualified


def extract_tables(sql_text: str) -> tuple[list[str], list[str]]:
    """Devuelve (tables, tables_qualified) dedup + orden alfabético.

    LÍMITES DECLARADOS (aceptados; el resultado es SOLO informativo):
    - No elimina comentarios `--` ni `/* */` antes de matchear: una sentencia
      dentro de un comentario cuenta como mención (falso positivo posible).
    - No ve SQL dinámico (EXEC / sp_executesql con strings concatenados).
    - No resuelve sinónimos ni vistas intermedias.
    - Descarta tablas temporales (#t) y variables de tabla (@t).
    """
    tables: set[str] = set()
    qualified: set[str] = set()
    for pattern in _TABLE_PATTERNS:
        for match in pattern.finditer(sql_text):
            table, qual = _clean_identifier(match.group(1))
            if table:
                tables.add(table)
            if qual:
                qualified.add(qual)
    return sorted(tables), sorted(qualified)
```

**Tests PRIMERO — `tests/test_plan180_extract.py`:**
- `test_ticket_prior_art_literal` (KPI-4): `infer_ticket("trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql") == "600804"` (el `1` de la carpeta NO gana: tiene menos de 4 dígitos y además el nombre matchea primero).
- `test_ticket_en_carpeta`: `infer_ticket("trunk/BD/601234/alta_indice.sql") == "601234"`.
- `test_ticket_ausente_none`: `infer_ticket("trunk/BD/utils/helpers.sql") is None`.
- `test_extract_todas_las_sentencias` (KPI-4): un SQL fixture con las 5 familias (`CREATE TABLE dbo.T1`, `ALTER TABLE [dbo].[T2]`, `INSERT INTO T3`, `UPDATE "T4" SET x=1`, `DELETE FROM db2.T5`, `MERGE INTO T6`) ⇒ `tables == ["T1","T2","T3","T4","T5","T6"]` y `tables_qualified` contiene `"DBO.T1"`, `"DBO.T2"`, `"DB2.T5"`.
- `test_extract_descarta_temporales`: `INSERT INTO #tmp` y `UPDATE @var SET` ⇒ ambos ignorados.
- `test_extract_dedup_y_orden`: la misma tabla mencionada 3 veces aparece 1 vez; salida ordenada.
- `test_extract_case_insensitive`: `insert into ridioma` ⇒ `["RIDIOMA"]`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan180_extract.py -q`
**Criterio (binario):** 7 tests verdes; el módulo NO importa `sqlalchemy` ni nada de conexión (`grep -n "import" services/dbcompare_repo_scripts.py` sin hits de red/BD).
**Flag:** sin efecto (sin llamadores). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Escáner read-only + índice persistido atómico

**Objetivo:** `build_index()` que escanea el workspace activo con globs/cap/exclusiones y persiste RepoScriptIndex v1; `load_index()` defensivo.
**Valor:** el índice existe y es barato, determinista y truncation-reportante.

**Archivo a editar:** `services/dbcompare_repo_scripts.py` — agregar:

```python
_EXCLUDED_DIR_NAMES = {
    "node_modules", ".git", ".svn", "venv", ".venv", "bin", "obj",
    "packages", "dist", "build", "__pycache__", ".vs",
}


def _index_path() -> Path:
    d = runtime_paths.data_dir() / _INDEX_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d / "index.json"


def _globs() -> list[str]:
    import config as _config
    raw = str(getattr(_config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_GLOBS",
                      "trunk/BD/**/*.sql,**/BD/**/*.sql"))
    return [g.strip() for g in raw.split(",") if g.strip()]


def _max_files() -> int:
    import config as _config
    try:
        val = int(getattr(_config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_MAX_FILES", 5000))
    except (TypeError, ValueError):
        val = 5000
    return max(100, min(val, 50000))


def _iter_sql_files(root: Path, globs: list[str], cap: int):
    """Camina los globs en orden, salteando _EXCLUDED_DIR_NAMES en cualquier
    posición de la ruta relativa; dedup de rutas; corta en `cap` archivos.
    Retorna (paths_ordenadas, truncated)."""
    seen: set[str] = set()
    out: list[Path] = []
    truncated = False
    for pattern in globs:
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            if any(part in _EXCLUDED_DIR_NAMES for part in rel.parts):
                continue
            key = rel.as_posix()
            if key in seen:
                continue
            if len(out) >= cap:
                truncated = True
                return out, truncated
            seen.add(key)
            out.append(p)
    return out, truncated


def build_index() -> dict | None:
    """Escanea el workspace ACTIVO (runtime_paths._active_workspace_root(),
    runtime_paths.py:66) y persiste el índice atómico. None si no hay workspace.
    READ-ONLY sobre el workspace: la única escritura es el index.json en data_dir()."""
    root = runtime_paths._active_workspace_root()
    if root is None:
        return None
    globs = _globs()
    cap = _max_files()
    files, truncated = _iter_sql_files(root, globs, cap)
    scripts = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            stat = path.stat()
        except OSError:
            continue  # archivo desaparecido/inaccesible: se saltea, no rompe
        tables, tables_qualified = extract_tables(text)
        scripts.append({
            "path": rel,
            "ticket": infer_ticket(rel),
            "tables": tables,
            "tables_qualified": tables_qualified,
            "mtime": int(stat.st_mtime),
            "size_bytes": int(stat.st_size),
            "sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        })
    scripts.sort(key=lambda s: s["path"])
    from datetime import datetime, timezone
    index = {
        "version": INDEX_VERSION,
        "workspace_root": str(root),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "globs": globs,
        "files_scanned": len(scripts),
        "truncated": truncated,
        "scripts": scripts,
    }
    path = _index_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))
    return index


def load_index() -> dict | None:
    path = _index_path()
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if doc.get("version") != INDEX_VERSION:
        return None
    return doc
```

Decisiones declaradas:
- **Encoding**: `read_text(encoding="utf-8", errors="replace")` — determinista y sin dependencias de detección; los `.sql` legacy en latin-1 producen U+FFFD en comentarios/acentos, pero los IDENTIFICADORES de tablas (ASCII en la convención RS) sobreviven intactos, que es lo único que la extracción necesita. El `sha256_12` se calcula sobre el texto YA decodificado (consistente entre corridas).
- **Refresco**: SOLO bajo demanda (POST refresh, F4) + auto-escaneo inline en el primer GET cuando `load_index()` es `None` y hay workspace (onboarding casi nulo: el panel aparece solo, sin que el operador toque nada). NO hay invalidación por mtime en cada GET: eso re-escanearía el árbol en cada render (caro); la evidencia de que el equilibrio correcto es "manual + primera vez" es el cap + workspace potencialmente enorme. NO hay daemon (§3).

**Tests PRIMERO — `tests/test_plan180_scanner.py`** (fixtures: `tmp_path/ws` como workspace fake con árbol `trunk/BD/...`; `monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: ws)` — precedente literal `tests/test_runtime_paths.py:36`; `monkeypatch.setattr(dbcompare_repo_scripts.runtime_paths, "data_dir", lambda: tmp_path / "data")` para el índice):
- `test_sin_workspace_none` (KPI-2): `_active_workspace_root` → `None` ⇒ `build_index() is None`, sin excepción.
- `test_indexa_convencion_prior_art`: árbol con `trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql` (contenido `INSERT INTO RIDIOMA ...`) ⇒ 1 script con `ticket=="600804"`, `tables==["RIDIOMA"]`, `path` posix relativo.
- `test_indice_determinista` (KPI-3): dos `build_index()` seguidos ⇒ `scripts` idénticos (comparación de la lista completa).
- `test_cap_reportado` (KPI-6): `MAX_FILES=... ` no — el cap se monkeypatchea vía `config.config` a 3 (nota: `_max_files` clampa a `min 100`; para el test, monkeypatchear `dbcompare_repo_scripts._max_files` directo a `lambda: 3`) con 5 archivos ⇒ `files_scanned==3`, `truncated is True`.
- `test_skip_dirs_excluidos`: un `.sql` bajo `ws/node_modules/x/BD/a.sql` y otro bajo `ws/.git/BD/b.sql` ⇒ NO aparecen.
- `test_workspace_intacto` (KPI-7): snapshot de `{path: mtime}` del árbol antes y después de `build_index()` ⇒ idéntico, y no aparece ningún archivo nuevo bajo `ws`.
- `test_load_index_corrupto_none`: `index.json` con basura ⇒ `load_index() is None`.
- `test_escritura_atomica_sin_tmp`: tras `build_index()` no queda `index.json.tmp`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan180_scanner.py -q`
**Criterio (binario):** 8 tests verdes.
**Flag:** los helpers leen `config.config` (hot-apply); el gate 403 llega en F4. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — Cobertura del diff: `match_diff_items` (pura)

**Objetivo:** cruzar los items de un SchemaDiff v1 con el índice y devolver candidatos rankeados.
**Valor:** la respuesta automática a "¿esto ya tiene script?".

**Archivo a editar:** `services/dbcompare_repo_scripts.py` — agregar:

```python
def match_diff_items(diff: dict, index: dict) -> dict:
    """Cruza items del SchemaDiff v1 (services/dbcompare_diff.py:311-331) con el
    RepoScriptIndex v1. PURA: no lee disco ni red. SOLO informa (HITL).

    Regla de matching (literal):
    - object_type "table" y "view": candidato = script cuyo `tables` contiene
      NAME.upper() O cuyo `tables_qualified` contiene f"{SCHEMA}.{NAME}".upper().
    - object_type "sequence": candidatos SIEMPRE [] (regla explícita: la
      extracción de F1 no captura sentencias de secuencias).
    - Ranking de candidatos: mtime descendente; empate -> path ascendente.
    """
    scripts = index.get("scripts") or []
    out_items = []
    covered = 0
    for item in diff.get("items") or []:
        name_u = str(item.get("name") or "").upper()
        qual_u = f"{str(item.get('schema') or '').upper()}.{name_u}"
        if item.get("object_type") == "sequence":
            candidates = []
        else:
            candidates = [
                s for s in scripts
                if name_u in (s.get("tables") or []) or qual_u in (s.get("tables_qualified") or [])
            ]
            candidates.sort(key=lambda s: (-int(s.get("mtime") or 0), s.get("path") or ""))
        if candidates:
            covered += 1
        out_items.append({
            "object_type": item.get("object_type"),
            "schema": item.get("schema"),
            "name": item.get("name"),
            "action": item.get("action"),
            "severity": item.get("severity"),
            "candidates": [
                {"path": s["path"], "ticket": s.get("ticket"), "mtime": s.get("mtime")}
                for s in candidates[:10]  # cap de candidatos por ítem, declarado
            ],
        })
    return {
        "items": out_items,
        "covered_count": covered,
        "total_count": len(out_items),
    }
```

**Tests PRIMERO — `tests/test_plan180_coverage.py`** (fixtures dict a mano, sin disco):
- `test_cobertura_2_de_3` (KPI-5): diff con 3 items tabla (`RIDIOMA`, `RTABL`, `RNUEVA`) e índice con scripts que mencionan `RIDIOMA` y `RTABL` ⇒ `covered_count == 2`, `total_count == 3`, `RNUEVA` con `candidates == []`.
- `test_match_calificado`: item `schema="dbo", name="RIDIOMA"` matchea script que solo trae `tables_qualified=["DBO.RIDIOMA"]`.
- `test_view_matchea_como_tabla` (KPI-5): item `object_type="view"` cuyo nombre aparece en `tables` de un script ⇒ candidato.
- `test_sequence_sin_candidatos` (KPI-5): item `object_type="sequence"` con nombre presente en el índice ⇒ `candidates == []` igual.
- `test_ranking_mtime_desc` (KPI-5): 2 scripts candidatos con mtimes distintos ⇒ el más nuevo primero; empate ⇒ orden por path.
- `test_case_insensitive`: item `name="ridioma"` matchea `tables=["RIDIOMA"]`.
- `test_cap_10_candidatos`: 12 scripts que mencionan la misma tabla ⇒ 10 candidatos.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan180_coverage.py -q`
**Criterio (binario):** 7 tests verdes; la función no importa nada nuevo.
**Flag:** N/A (pura). **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F4 — API: blueprint nuevo `db_compare_repo`

**Objetivo:** exponer índice, refresh y cobertura bajo `/api/db-compare/...` sin tocar `api/db_compare.py`.
**Valor:** la UI (F5) y el triage futuro (176) consumen el puente por HTTP.

**Archivo a crear:** `Stacky Agents/backend/api/db_compare_repo.py`:

```python
"""Plan 180 — API del puente diff→repo. Blueprint SEPARADO de api/db_compare.py
(que toca el plan 176) para colisión de merge cero. Mismo url_prefix, nombre
distinto: Flask lo admite; las rutas no se pisan (tabla verificada
api/db_compare.py:52-411 — /repo-scripts y /runs/<run_id>/repo-coverage libres)."""
from flask import Blueprint, jsonify

import config as _config
import runtime_paths
from services import dbcompare_repo_scripts, dbcompare_runs

bp = Blueprint("db_compare_repo", __name__, url_prefix="/db-compare")


def _require_bridge_enabled():
    # Idioma de api/db_compare.py:27-29 — la instancia de flags es config.config,
    # NO el módulo (gotcha: getattr(config, FLAG) da default y mata el branch OFF).
    if not getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False):
        return jsonify({"ok": False, "error": "Comparador de BD deshabilitado (STACKY_DB_COMPARE_ENABLED)."}), 403
    if not getattr(_config.config, "STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED", False):
        return jsonify({"ok": False, "error": "Puente al repo deshabilitado (STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED)."}), 403
    return None
```

Rutas EXACTAS (cada una arranca con `gate = _require_bridge_enabled(); if gate is not None: return gate`):

| Método y ruta | Función | Comportamiento |
|---|---|---|
| `GET /repo-scripts` | `get_repo_scripts_route` | `workspace = runtime_paths._active_workspace_root()`; si `None` ⇒ 200 `{"ok": true, "index": null, "workspace": null}` (KPI-2). Si hay workspace: `index = load_index()`; si es `None` ⇒ `index = build_index()` (auto-escaneo primera vez, F2); 200 `{"ok": true, "index": index, "workspace": str(workspace)}` |
| `POST /repo-scripts/refresh` | `refresh_repo_scripts_route` | escaneo forzado: `index = build_index()`; si `None` (sin workspace) ⇒ 200 `{"ok": true, "index": null, "workspace": null}`; si no ⇒ 200 `{"ok": true, "index": index}` |
| `GET /runs/<run_id>/repo-coverage` | `run_repo_coverage_route` | `run = dbcompare_runs.get_run(run_id)` (`dbcompare_runs.py:207`); 404 `{"ok": false, "error": "run desconocido"}` si `None`; 409 `{"ok": false, "error": "la corrida no tiene diff (status != done)"}` si `run.get("diff")` es `None`; si `load_index()` es `None` ⇒ auto-escaneo como en GET; si sigue `None` ⇒ 200 `{"ok": true, "coverage": null, "workspace": null}`; si no ⇒ 200 `{"ok": true, "coverage": match_diff_items(run["diff"], index)}` |

**Registro:** `Stacky Agents/backend/api/__init__.py` — 2 líneas con el idioma exacto de `:57` y `:118`:
```python
from .db_compare_repo import bp as db_compare_repo_bp  # Plan 180 — puente diff→repo
...
api_bp.register_blueprint(db_compare_repo_bp)  # Plan 180 — url_prefix="/db-compare" → /api/db-compare/repo-scripts|runs/<id>/repo-coverage
```

**Tests PRIMERO — completar `tests/test_plan180_api.py`** (cliente Flask con el fixture de app de los tests dbcompare existentes; monkeypatch de `data_dir` y `_active_workspace_root` como en F2):
- `test_403_flags_off` (KPI-1): master OFF ⇒ 403 en las 3 rutas; master ON + bridge OFF ⇒ 403 en las 3.
- `test_sin_workspace_noop` (KPI-2): flags ON, `_active_workspace_root` → `None` ⇒ GET /repo-scripts 200 con `index null`.
- `test_get_autoescanea_primera_vez`: workspace fake con 1 script ⇒ primer GET construye y persiste el índice; segundo GET NO re-escanea (monkeypatch de `build_index` con contador ⇒ 1 sola llamada entre ambos GET).
- `test_refresh_fuerza_reescaneo`: POST refresh ⇒ `build_index` llamado aunque el índice exista.
- `test_coverage_run_inexistente_404`.
- `test_coverage_run_sin_diff_409`: run sembrado con `status="running", diff=None`.
- `test_coverage_feliz`: run sembrado `done` con diff fixture de F3 + índice sembrado ⇒ `coverage.covered_count == 2`.

**Comando:** `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/test_plan180_api.py -q`
**Criterio (binario):** 7 tests de F4 (más los 3 de F0 en el mismo archivo) verdes; `git diff --stat` NO lista `api/db_compare.py`.
**Flag:** doble gate 122+180 en cada ruta. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F5 — Frontend: panel de cobertura autocontenido

**Objetivo:** mostrar "N de M ítems del diff tienen script ticketeado candidato" con lista por ítem, en un componente nuevo con montaje de 1 línea.
**Valor:** el cruce manual desaparece de la vista del operador — lo ve resuelto arriba del diff.

**Archivos a crear:**

1. `frontend/src/components/dbcompare/repoCoverageTypes.ts` — tipos espejo del payload F4: `RepoScriptEntry`, `RepoScriptIndex`, `RepoCoverageCandidate`, `RepoCoverageItem`, `RepoCoverage` (claves EXACTAS del backend). NO editar `dbcompareTypes.ts` (lo toca el 176).
2. `frontend/src/components/dbcompare/repoCoverageLogic.ts` — funciones puras:
   - `coverageSummary(coverage: RepoCoverage | null): {covered: number; total: number; pct: number} | null` — `null` si `coverage` es `null` o `total_count === 0` (el panel no se renderiza).
   - `groupCandidatesByTicket(items: RepoCoverageItem[]): {ticket: string | null; paths: string[]}[]` — agrupación estable para el resumen por ticket, orden: tickets numéricos ascendente, `null` al final.
   - `severityOrder(items: RepoCoverageItem[]): RepoCoverageItem[]` — danger primero, después warn, después info; empate por `schema.name` ascendente (mismo criterio visual que el export md, `dbcompare_runs.py:305-309`).
3. `frontend/src/components/dbcompare/RepoCoveragePanel.tsx` — componente autocontenido:
   - Props: `{ runId: string }`.
   - Al montar (y al cambiar `runId`): `DbCompareRepo.runCoverage(runId)`. Si la promesa RECHAZA (403 flag OFF, red) o `coverage` es `null` o `coverageSummary` es `null` ⇒ `return null` (patrón health→null de `DbComparePage.tsx:41-45`; KPI-1: cero UI con flag OFF).
   - Render: encabezado "Cobertura del repo (scripts ticketeados)" + resumen "N de M ítems tienen script candidato" + lista `severityOrder`-ada: por ítem, nombre calificado + badges de candidatos (`ticket` + `path` truncado con title completo) + botón "Copiar ruta" (`navigator.clipboard.writeText`) + botón "Reescanear repo" que llama `DbCompareRepo.refresh()` y recarga.
   - CERO `style={{...}}`; clases nuevas en `dbcompare.module.css` (append al final): `.repoCoverageSection`, `.repoCoverageSummary`, `.repoCoverageRow`, `.repoCoverageTicket`, `.repoCoveragePath`, `.repoCoverageUncovered`, usando `var(--dbc-danger)`, `var(--dbc-warn)`, `var(--dbc-info)`, `var(--dbc-unchanged)` (tokens verificados en `dbcompare.module.css:10-27`).

**Archivos a editar (mínimos):**

4. `frontend/src/api/endpoints.ts` — agregar AL FINAL REAL del archivo (hoy 4228 líneas; el último export actual es el del resolutor de incidencias — verificar el final con `tail` al implementar, NO asumir que `DbCompare` de `:3967` sigue siendo el último):
   ```typescript
   // Plan 180 — Puente diff→repo (índice read-only de scripts SQL ticketeados).
   export const DbCompareRepo = {
     getIndex: () =>
       api.get<{ ok: boolean; index: RepoScriptIndex | null; workspace: string | null }>(
         "/api/db-compare/repo-scripts",
       ),
     refresh: () =>
       api.post<{ ok: boolean; index: RepoScriptIndex | null }>(
         "/api/db-compare/repo-scripts/refresh",
         {},
       ),
     runCoverage: (runId: string) =>
       api.get<{ ok: boolean; coverage: RepoCoverage | null }>(
         `/api/db-compare/runs/${encodeURIComponent(runId)}/repo-coverage`,
       ),
   };
   ```
   (import de tipos desde `../components/dbcompare/repoCoverageTypes`; usar los helpers `api.get`/`api.post` con el idioma exacto del objeto `DbCompare`, `endpoints.ts:3967-4068`.)
5. `frontend/src/components/dbcompare/DbComparePage.tsx` — EXACTAMENTE 2 ediciones sobre el archivo REAL de main:
   - 1 import: `import { RepoCoveragePanel } from "./RepoCoveragePanel";`
   - 1 elemento JSX dentro del fragmento del bloque results existente (`{view === "results" && activeRun && diff && (<> ... </>)}`, `DbComparePage.tsx:157-183`), inmediatamente DESPUÉS de la línea `{health?.data_diff_enabled && <DataParitySection run={activeRun} onRunUpdate={setActiveRun} />}` (`:181`) y ANTES del cierre `</>` (`:182`):
     ```tsx
     <RepoCoveragePanel runId={activeRun.run_id} />
     ```
   - Nada más: sin estado nuevo, sin efectos nuevos en la página.

**Tests PRIMERO — `frontend/src/components/dbcompare/repoCoverageLogic.test.ts`** (vitest por archivo, sin RTL/jsdom):
- `coverageSummary`: `null` input ⇒ `null`; `total_count 0` ⇒ `null`; 2/3 ⇒ `{covered: 2, total: 3, pct: 67}` (redondeo declarado `Math.round`).
- `groupCandidatesByTicket`: tickets `"600804"`, `"600123"`, `null` ⇒ orden `600123, 600804, null`; paths dedup.
- `severityOrder`: danger < warn < info estable; empate por nombre.

**Comandos:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/components/dbcompare/repoCoverageLogic.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio (binario):** vitest verde + `tsc --noEmit` limpio + `grep -c "style={{" RepoCoveragePanel.tsx` == 0 + `git diff` de `DbComparePage.tsx` con exactamente 2 hunks (import + JSX).
**Flag:** el panel se auto-oculta ante 403/null (KPI-1) — el frontend no lee flags. **Runtimes:** idéntico en los 3 (panel). **Trabajo del operador:** ninguno (el panel aparece solo cuando hay diff activo, workspace e índice con datos).

---

### F6 — Cierre y verificación integral

**Objetivo:** demostrar no-regresión y dejar el DoD auditable.

**Acciones:**
1. Verificar registro de los 4 tests backend en ambos runners (grep en `run_harness_tests.sh` y `.ps1`).
2. Correr POR ARCHIVO: los 4 `test_plan180_*.py` + `tests/test_harness_flags.py` + `tests/test_harness_flags_requires.py` + `tests/test_runtime_paths.py` (por el uso de `_active_workspace_root`) + los 3 de la serie dbcompare que tocan la API y runs: `tests/test_plan122_dbcompare_api.py`, `tests/test_plan123_dbcompare_api.py`, `tests/test_plan123_dbcompare_runs.py` — todos con `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m pytest tests/<archivo> -q`.
3. `cd "Stacky Agents/backend" && "./venv/Scripts/python.exe" -m compileall services/dbcompare_repo_scripts.py api/db_compare_repo.py` limpio (mitigación del gotcha PyInstaller collect-submodules: un SyntaxError en un submódulo nuevo aparece como `ModuleNotFoundError` tardío en el deploy congelado).
4. Frontend: `npx tsc --noEmit` + vitest del archivo de F5.
5. Smoke manual documentado en el PR (requiere un workspace real con `trunk/BD`):
   - Con proyecto activo apuntando a un repo RS real: abrir el Comparador, correr un compare `done` ⇒ el panel "Cobertura del repo" aparece bajo el diff con N/M y tickets reales.
   - `data\db_compare\repo_scripts\index.json` existe y sus `path` son relativos al workspace.
   - Botón "Reescanear repo" refresca tras agregar un `.sql` nuevo al repo.
   - Apagar `STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED` por UI ⇒ el panel desaparece en el próximo render del run (sin reinicio).

**Criterio (binario):** puntos 1-4 verdes; punto 5 documentado con resultados.
**Trabajo del operador:** ninguno.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Workspace enorme (monorepo con miles de `.sql`) | Primer GET lento o request colgado | Cap `MAX_FILES` (default 5000, editable por UI) + `_EXCLUDED_DIR_NAMES` (lista literal F2) + `truncated` REPORTADO (KPI-6) + refresh manual disponible; sin invalidación por mtime en GET (decisión declarada F2) |
| R2 | Regex de tablas con falsos positivos (sentencias en comentarios) o negativos (SQL dinámico, sinónimos) | Cobertura imprecisa | Límites DECLARADOS en el docstring de `extract_tables` (F1) y en la UI el dato es SOLO informativo: nunca excluye ni decide nada (§3); el operador ve la ruta y el ticket y juzga |
| R3 | Granularidad de `mtime` (FAT/2s, copias que preservan fechas) | Ranking de candidatos aproximado | Aceptado y declarado: el ranking es heurístico de conveniencia (más nuevo primero); el empate cae a orden por path, determinista |
| R4 | Encoding legacy (latin-1) en `.sql` viejos | Texto con U+FFFD | Decisión literal F2: `errors="replace"` — los identificadores ASCII de la convención RS sobreviven; sin dependencia de detección de charset |
| R5 | Ítems del diff sin tabla asociada (sequences) o views sin mención | Cobertura "no cubierto" engañosa | Regla explícita (F3): sequences devuelven `[]` SIEMPRE (declarado en el contrato de `match_diff_items`); views matchean por nombre igual que tablas; el panel distingue visualmente "sin candidatos" sin implicar "falta script" |
| R6 | `index.json` corrupto o de versión vieja | Panel roto | `load_index()` defensivo ⇒ `None` ⇒ auto-reescaneo en el próximo GET (F2/F4); ningún endpoint crashea |
| R7 | Colisión de merge en `DbComparePage.tsx`/`endpoints.ts` con 176/178 | Duplicado silencioso | Guía de merge en §2bis: conservar ambos lados + `npx tsc --noEmit` + grep de `DbCompareRepo` esperando 1 declaración |
| R8 | Sesión paralela ocupa el número 180 antes del commit | Colisión de numeración (precedente: 171) | Número recalculado listando `docs/` inmediatamente antes del Write; si al commitear existe otro 180, renumerar el archivo completo al primer libre ANTES de commitear |
| R9 | El operador interpreta "cubierto" como "no hay que hacer nada" | Decisión errada por confianza ciega | El panel dice "candidato" (no "resuelto"), muestra ticket+ruta para verificación humana, y este plan NO integra con exclusiones del triage (176) ni con generación de scripts (125) |
| R10 | `_active_workspace_root` es privada-por-convención y podría cambiar | Rotura futura del puente | Precedente de uso como seam oficial: 12 monkeypatches en `tests/test_runtime_paths.py:36-171`; además `repo_root()` (`runtime_paths.py:158`) ya la consume — cualquier cambio de firma rompería tests core del repo antes que este plan |

---

## 7. Fuera de scope (diferidos explícitos de este plan)

- **Excluir/auto-resolver ítems del diff por cobertura**: NUNCA — violaría HITL; ni en este plan ni en futuros (la cobertura es información, la decisión es humana).
- **Parser SQL completo** (comentarios, SQL dinámico, sinónimos, CTEs): fuera; los límites del regex quedan declarados en F1.
- **Escaneo de repos remotos** (GitLab/ADO por API): fuera; solo filesystem local del workspace activo.
- **Integración con el triage del 176**: condicional futura (§2bis); nada se implementa acá.
- **Ejecución o edición de scripts del repo**: PROHIBIDO por doctrina de la serie (Stacky genera/observa, nunca ejecuta).
- **Watch de filesystem / daemon de re-indexado**: fuera; refresh manual + auto-primera-vez alcanza para v1 (y el mandato de este plan es cero threads nuevos).
- **Cobertura del data-diff (126)**: fuera de v1; `match_diff_items` opera sobre el SchemaDiff; extenderlo a tablas del data-diff es aditivo futuro.

---

## 8. Glosario, orden de implementación y DoD global

### Glosario

- **Puente diff→repo**: el conjunto índice + cobertura + panel de este plan.
- **Script ticketeado**: archivo `.sql` del repo del producto cuyo nombre o carpeta contiene el número de ticket (convención `glossary.py:25`).
- **RepoScriptIndex v1**: contrato del índice persistido (§4).
- **Cobertura**: para un diff dado, qué ítems tienen al menos un script candidato que menciona su tabla/view.
- **Candidato**: script cuyo set de tablas extraídas contiene el nombre del ítem (regla F3) — es una PISTA para el operador, no un veredicto.
- **Workspace activo**: `workspace_root` del proyecto activo de Stacky (`runtime_paths._active_workspace_root()`, `runtime_paths.py:66`).

### Orden de implementación (estricto)

F0 (flags) → F1 (extracción pura) → F2 (escáner/índice) → F3 (cobertura pura) → F4 (API) → F5 (frontend) → F6 (cierre). F1 y F3 son puras y podrían desarrollarse en paralelo por dos personas, pero el orden de commit es el declarado.

### Definition of Done global

1. Los 7 KPIs de §1.3 verificados con sus tests/comandos.
2. Los 4 archivos `tests/test_plan180_*.py` verdes POR ARCHIVO y registrados en ambos runners.
3. `tests/test_harness_flags.py`, `tests/test_harness_flags_requires.py`, `tests/test_runtime_paths.py` y los 3 archivos dbcompare de F6 punto 2 verdes sin editarlos.
4. Frontend: vitest de `repoCoverageLogic.test.ts` verde, `npx tsc --noEmit` limpio, 0 `style={{` en los `.tsx` nuevos.
5. `harness_defaults.env` regenerado por script (las 3 flags nuevas presentes).
6. `git diff --stat` solo lista los archivos de la fila "180" de la tabla §2bis — en particular NO lista `api/db_compare.py`, `dbcompare_snapshot.py`, `dbcompare_diff.py`, `dbcompare_runs.py`, `dbcompare_scripts.py` ni `SummaryHero.tsx`.
7. Con `STACKY_DB_COMPARE_REPO_BRIDGE_ENABLED=false`: API nueva 403, panel invisible, conducta global idéntica a main (KPI-1).
8. Smoke manual de F6 documentado en el PR.
