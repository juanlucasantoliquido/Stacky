# Plan 130 — Gate determinista de integridad de código pre-publicación (sintaxis + imports, sin IA)

**Estado:** CRITICADO — APROBADO-CON-CAMBIOS (v2, 2026-07-14; v1 2026-07-13)

**Changelog v1 → v2 (crítica adversarial, juez `StackyArchitectaUltraEficientCode`):**
- **C1 (IMPORTANTE):** el snippet de `code_integrity_route()` en F2 declaraba
  `import config as _config_mod` (alias nuevo) contradiciendo su propia instrucción de
  "reusar el import existente" — `api/diag.py:26` YA importa `config as _config` y lo usa
  como `_config.config.X` en `api/diag.py:364`. Corregido: el snippet reusa `_config`
  directamente, sin import local nuevo.
- **C2 (IMPORTANTE):** F0 citaba `_CURATED_DEFAULTS_ON (:465)` como "AL FINAL" del set,
  pero `:465` es la línea de APERTURA (`_CURATED_DEFAULTS_ON = {`); el cierre real
  (`}`) está en `:550`, después de `"STACKY_ADO_PREWARM_ENABLED",`. Verificado por lectura
  directa del archivo. Corregido con la línea real + ancla de búsqueda por contenido (no
  por número de línea a ciegas).
- **C3 (MENOR):** F0 citaba `config.py:940-941` para el patrón espejo
  `STACKY_DEVOPS_PANEL_ENABLED` (con un typo de mayúsculas en la prosa,
  "STACKY_DEVOps_PANEL_ENABLED"); la ubicación real verificada es `config.py:930-931`.
  Corregido línea y casing.
- **[ADICIÓN ARQUITECTO]** F5 ahora agrega un chequeo INFORMATIVO (no cambia exit code)
  del CLI de integridad al INICIO de `run_harness_tests.ps1`/`.sh`, antes del loop de
  pytest — reusa el CLI de F2 para señalar en segundos la causa raíz real cuando un
  `SyntaxError` en un módulo compartido hace fallar la COLECCIÓN de decenas de archivos
  del ratchet a la vez (mismo patrón "collect-submodules silencioso" del §2, aplicado al
  loop de tests en vez de a PyInstaller). Costo cero, sin flag, sin tocar el contrato de
  salida del ratchet.
- Todas las citas de código restantes (`api/diag.py:40`, `DiagnosticsPage.tsx:13-14/206`,
  `Prepare-Publication.ps1:11-23/20/40-80/346-376`, `build_release.ps1:703-719`,
  `App.tsx:250`, `test_plan87_devops_endpoints.py:6-29`, `harness_flags.py:103/111`,
  `test_harness_flags.py:465/510`, `harness_flags_help.py:268`, patrón `FlagSpec` con
  `group="global"`/`env_only`/`requires`) fueron verificadas contra el código REAL en HEAD
  de este worktree y son EXACTAS — sin cambios.

**Dependencias:** ninguna dura. Reusa el pipeline de publicación existente (`deployment/Prepare-Publication.ps1`), el blueprint `diag` (`api/diag.py:40`) y la página Diagnóstico (siempre visible, sin gate de sección — `App.tsx:250`).
**Ortogonal a:** Plan 102 (orquestador HITL de publicación: sus enganches `preflightSlot`/`beforeCommit` quedan como punto de integración FUTURO, declarado en §7), Plan 127-C3 (doctor DevOps con IA local: narrativo y por sección; esto es determinista, sin IA y pre-build), Planes 93/96 (semáforo/doctor de pipelines CI REMOTOS), Plan 129 (paleta global — no comparte archivos). NO toca `App.tsx`.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Los contratos JSON, reglas de resolución
> de imports, bloques PowerShell y nombres son LITERALES: prohibido desviarse de los
> nombres exactos, prohibido "mejorar" el alcance. Todo lo ambiguo ya fue decidido acá.

---

## 1. Objetivo + KPI

"Preparar Publicación" se rompió DOS veces por errores de código triviales detectados
tardísimo y con síntomas engañosos:

1. **Incidente real 2026-07-10:** un `SyntaxError` en `api/devops_servers.py:223`
   (Plan 118) rompió la publicación completa.
2. **Gotcha documentado (memoria del repo):** un fallo del smoke test del release con
   `ModuleNotFoundError` en un submódulo = en realidad un `SyntaxError` real en ese
   submódulo — PyInstaller `collect-submodules` se lo traga en silencio y el diagnóstico
   aparente ("problema de entorno/build") es FALSO.

Hoy el PRIMER punto de detección es el smoke test **post-build**
(`deployment/build_release.ps1:703-719`: pytest de `tests\test_release_smoke.py` DESPUÉS
de construir el release), es decir: minutos de build tirados, mensaje críptico, y encima
existe `-SkipSmokeTest` (`Prepare-Publication.ps1:20`, propagado en `:408-409`) que deja
publicar sin red alguna.

Este plan agrega un **gate determinista que corre en segundos ANTES del build**:

- **CHECK-1 (sintaxis):** `ast.parse` en memoria de TODOS los `.py` del backend
  (sin ejecutar código, sin escribir `.pyc`). Un `SyntaxError` se reporta con
  archivo:línea exactos — el incidente 1 y la causa raíz del incidente 2, atrapados
  al instante.
- **CHECK-2 (imports de primera parte):** por AST, todo `import`/`from ... import` cuyo
  módulo raíz sea del propio backend debe resolver a un archivo/paquete existente —
  atrapa módulos renombrados/borrados (la clase `ModuleNotFoundError`) sin importar nada.

El gate vive en 3 superficies con UNA sola implementación (`services/code_integrity.py`):
hook fail-fast en `Prepare-Publication.ps1` (automático, con bypass `-SkipCodeIntegrity`),
CLI `backend/scripts/check_code_integrity.py` (usable a mano y por el ratchet), y
`GET /api/diag/code-integrity` con una card on-demand en la página Diagnóstico.

**KPIs (binarios):**

- **KPI-1 (los 2 incidentes, atrapados):** fixtures que reproducen ambos patrones
  (SyntaxError en un submódulo; módulo de primera parte inexistente) → detectados con
  `file` + `line` exactos (tests F1 casos 4 y 6).
- **KPI-2 (cero falsos positivos):** `run_checks()` sobre el backend REAL en HEAD limpio
  → `ok: true` (test integrador F1 caso 13; si falla, hay código roto DE VERDAD en el
  working tree — eso es el producto funcionando, no un bug del test).
- **KPI-3 (fail-fast, fail-open correcto):** con hallazgos → la publicación ABORTA antes
  de tocar procesos/build (exit 1 → `throw`); con el verificador caído/entorno roto →
  WARN y continúa (exit 2 / try-catch): el gate atrapa código roto, no bloquea por
  entorno (F3).
- **KPI-4 (kill-switch limpio):** flag OFF → endpoint 404 y card ausente;
  `-SkipCodeIntegrity` → `Prepare-Publication.ps1` byte-idéntico al flujo actual (F0/F2/F3).

## 2. Por qué ahora / gap que cierra (evidencia verificada en HEAD)

- `deployment/Prepare-Publication.ps1` NO corre ningún análisis estático del árbol
  backend: tras el bloque de parámetros (`:11-23`) y helpers (`:40-80`) pasa directo a
  detener procesos y buildear. El único chequeo de código es el smoke POST-build
  (`build_release.ps1:703-719`), que además es salteable.
- El gotcha del `ModuleNotFoundError` engañoso está documentado en la memoria del repo
  como trampa recurrente: el operador pierde tiempo diagnosticando "entorno" cuando es
  un `SyntaxError` del código. Diagnóstico correcto en segundos = valor directo.
- Ningún plan existente cubre esto: 93/96 son sobre pipelines CI remotos; 102 orquesta
  la publicación (proceso) y declara enganches de veto pero NINGÚN check de código;
  116 es red/conexiones; 127-C3 es un doctor narrativo CON IA por sección (no
  determinista, no pre-build, no bloquea nada).
- Todo el sustrato para las 3 superficies ya existe: blueprint `diag` con url_prefix
  `/diag` (`api/diag.py:40`), página Diagnóstico con cards (`DiagnosticsPage.tsx:13-14`
  monta `HarnessHealthCard` y `OperationalHealthCard`), patrón de scripts en
  `backend/scripts/`, y helpers `Write-Step/Write-OK/Write-Warn` + `$appRoot` en el ps1
  (`Prepare-Publication.ps1:27-54`).
- Meta-valor: cada mejora de Stacky llega al deploy VÍA la publicación. Blindar ese
  camino protege el ciclo completo de evolución.

## 3. Principios y guardarraíles (NO negociables)

1. **Determinista y sin IA:** solo `ast.parse` + recorrido de filesystem. Prohibido
   invocar modelos (ni locales), runtimes, red o subprocesos desde el servicio.
2. **Cero ejecución y cero escritura:** el código analizado JAMÁS se importa ni ejecuta
   (`ast.parse`, nunca `import`/`exec`/`importlib`); no se escribe NINGÚN archivo (ni
   `.pyc` — nada de `py_compile`/`compileall`). Test F1 caso 12 lo congela
   (`__pycache__` inexistente tras correr).
3. **Human-in-the-loop:** el gate BLOQUEA con evidencia (archivo:línea) pero el operador
   siempre puede decidir: `-SkipCodeIntegrity` en el ps1, flag OFF para la card. Nada se
   "auto-arregla".
4. **Paridad 3 runtimes:** herramienta local determinista; cero interacción con Codex /
   Claude Code / Copilot. Idéntica bajo cualquiera. Degradación: entorno sin venv/python
   → WARN y la publicación continúa (fail-open de entorno, fail-closed de código).
5. **Cero trabajo del operador:** el hook corre AUTOMÁTICO dentro del flujo de
   publicación existente; la card es on-demand. Flag `STACKY_CODE_INTEGRITY_ENABLED`
   default **ON** (directiva del operador 2026-07-12, patrón triple Plan 127 §3.6),
   kill-switch UI-editable, categoría EXISTENTE `capacidades_optin`.
6. **La flag gatea SOLO el endpoint/card.** `Prepare-Publication.ps1` es un script de
   build independiente del backend: NO consulta flags; su kill-switch es
   `-SkipCodeIntegrity` (paridad con `-SkipSmokeTest`). Declarado, no accidental.
7. **Gotchas de flags default ON (patrón Plan 127 §3.6):** FlagSpec `default=True` +
   comentario de decisión; key AL FINAL de `_CURATED_DEFAULTS_ON`
   (`tests/test_harness_flags.py:465`); `config.py` con default `"true"`. SIN `requires`,
   SIN `env_only`. `harness_defaults.env` NO se regenera y NO lleva línea `=false`
   (test negativo, Plan 127 §3.11).
8. **PowerShell 5.1 estricto:** el bloque nuevo del ps1 va en ASCII (sin acentos, como el
   resto del script), sin `&&`/`||`, con `throw` (el script ya corre con
   `$ErrorActionPreference = "Stop"`, `:25`).
9. **Al implementar:** `config.py`, `harness_flags.py`, `api/diag.py`, `endpoints.ts` y
   `DiagnosticsPage.tsx` pueden tener WIP ajeno → staging quirúrgico por hunk/pathspec;
   PROHIBIDO `git stash`/`reset`/`checkout` de limpieza; `git status` final.
10. **Colisión de numeración (riesgo VIVO):** hay un loop paralelo proponiendo planes
    (el 129 nació duplicado el 2026-07-13). Quien implemente debe verificar que
    `130_PLAN_GATE_INTEGRIDAD_CODIGO_PREPUBLICACION.md` sigue siendo el único `130_*`.

## 4. Contratos congelados

### 4.1 Reglas de escaneo (LITERALES)

```python
_EXCLUDED_DIRS = {".venv", "__pycache__", "node_modules", ".git", ".pytest_cache", "data", "outputs"}
_PY_SUFFIX = ".py"
```

- Raíz por defecto: `backend_root() = Path(__file__).resolve().parents[1]` (el módulo
  vive en `backend/services/` → raíz = `backend/`).
- Recorrido recursivo saltando (por NOMBRE de directorio, en cualquier nivel) los
  `_EXCLUDED_DIRS`. Solo archivos `*.py`. Lectura con
  `read_text(encoding="utf-8", errors="replace")`.
- `file` en los reportes: ruta RELATIVA a la raíz, SIEMPRE posix (`api/devops_servers.py`).

### 4.2 Reglas de resolución de imports (LITERALES — deciden CHECK-2)

```python
def first_party_names(root: Path) -> set[str]:
    # Nombres de primera parte = en el NIVEL RAÍZ de backend/:
    #  - cada archivo *.py → su stem ("app", "config", "models", "db", ...)
    #  - cada directorio NO excluido que contenga __init__.py → su nombre ("api", "services", ...)

def resolve_module(root: Path, dotted: str) -> bool:
    # "a.b.c" resuelve si existe root/a/b/c.py O root/a/b/c/__init__.py.
    # "a" resuelve si existe root/a.py O root/a/__init__.py.
```

Sobre cada archivo parseado (AST), se validan:
- `import X.Y.Z` → si `X` ∈ primera parte: exigir `resolve_module(root, "X.Y.Z")`.
- `from X.Y import Z` → si `X` ∈ primera parte: exigir `resolve_module(root, "X.Y")`.
  Los NOMBRES importados (`Z`) NO se validan jamás (pueden ser atributos — estáticamente
  indecidible; regla anti-falso-positivo).
- Import RELATIVO `from .foo import bp` (nivel `level>=1`): base = directorio del archivo
  menos `level-1` niveles; exigir que `base/foo.py` o `base/foo/__init__.py` exista.
  `from . import x` (module None) → validar solo que la base exista (no los nombres).
- **Exención try/except (anti-falso-positivo, congelada):** los imports que están DENTRO
  del `body` de un `ast.Try` cuyo algún handler captura `ImportError` o
  `ModuleNotFoundError` (o `Exception`) se EXENTÚAN de CHECK-2 (patrón legítimo de
  feature opcional). Implementación: pre-recorrer los `ast.Try` y juntar los `lineno` de
  los imports exentos en un set.
- Terceros (`flask`, `sqlalchemy`, …): ignorados SIEMPRE (no ∈ primera parte).

### 4.3 Contrato del reporte (JSON — idéntico en servicio, CLI --json y endpoint)

```json
{
  "ok": false,
  "root": "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend",
  "files_scanned": 310,
  "elapsed_ms": 1240,
  "syntax_errors": [
    {"file": "api/devops_servers.py", "line": 223, "message": "invalid syntax"}
  ],
  "broken_imports": [
    {"file": "api/__init__.py", "line": 55, "import": "api.pr_reviewx", "message": "modulo de primera parte no encontrado"}
  ]
}
```

Reglas duras:
- `ok = (syntax_errors == [] and broken_imports == [])`. Todas las claves SIEMPRE presentes.
- `SyntaxError` de `ast.parse` → `line = exc.lineno or 0`, `message = exc.msg`.
  `ValueError` (bytes NUL) → mismo shape con `line = 0`.
- Un archivo con error de sintaxis NO se analiza para imports (no hay AST).
- Orden estable: hallazgos ordenados por (`file` ASC, `line` ASC).

### 4.4 Códigos de salida del CLI (congelados)

| exit | significado | efecto en el ps1 |
|---|---|---|
| 0 | `ok: true` | `Write-OK`, continúa |
| 1 | hay `syntax_errors` y/o `broken_imports` | `throw` → publicación ABORTADA |
| 2 | error interno del verificador | `Write-Warn`, continúa (fail-open de entorno) |

Salida humana (default): líneas `file:line — message` por hallazgo + resumen
`"[code-integrity] N archivos, M hallazgos, X ms"`. Con `--json`: SOLO el JSON de §4.3.

### 4.5 Contrato HTTP (congelado)

`GET /api/diag/code-integrity`:
- Flag OFF → **404** `{"ok": false, "error": "code_integrity_disabled", "message": "El verificador de integridad está deshabilitado (STACKY_CODE_INTEGRITY_ENABLED)."}`
- OK → **200** con el JSON de §4.3.
- Excepción interna → **200** `{"ok": false, "error": "<NombreDeClase>"}` (SOLO
  `type(exc).__name__`, nunca `str(exc)` — no filtrar paths/detalles).

---

## 5. Fases

### F0 — Flag `STACKY_CODE_INTEGRITY_ENABLED` (default ON, patrón triple Plan 127 §3.6)

**Objetivo:** declarar la flag bool default ON, UI-editable, sin romper la suite de flags.
**Valor:** endpoint/card vivos el día uno + kill-switch UI.

**Archivos a editar (5):**
1. `Stacky Agents/backend/services/harness_flags.py`:
   ```python
   FlagSpec(
       key="STACKY_CODE_INTEGRITY_ENABLED",
       type="bool",
       label="Verificador de integridad de código",
       description=(
           "Gate determinista pre-publicación: sintaxis (ast.parse) e imports de "
           "primera parte de todo el backend, en segundos, sin ejecutar código y sin IA. "
           "Expone GET /api/diag/code-integrity y la card en Diagnóstico."
       ),
       group="global",
       default=True,  # Default ON (activado 2026-07-13, decisión explícita del operador — patrón triple Plan 127 §3.6)
   ),
   ```
   (al FINAL del `FLAG_REGISTRY`; SIN `requires=`, SIN `env_only=`)
   + agregar `"STACKY_CODE_INTEGRITY_ENABLED"` a la tupla EXISTENTE
   `_CATEGORY_KEYS["capacidades_optin"]` (dict en `harness_flags.py:111`, buscar la clave
   por nombre).
2. `Stacky Agents/backend/tests/test_harness_flags.py` — agregar
   `"STACKY_CODE_INTEGRITY_ENABLED",` AL FINAL del set `_CURATED_DEFAULTS_ON`, INMEDIATAMENTE
   ANTES del `}` de cierre. El set ABRE en `:465` (`_CURATED_DEFAULTS_ON = {`) pero el
   CIERRE real está en `:550`, justo después de `"STACKY_ADO_PREWARM_ENABLED",` — usar ESE
   string como ancla de búsqueda (Edit por contenido), no el número de línea a ciegas.
   Comentario `# Plan 130 — default ON (operador 2026-07-13)`.
3. `Stacky Agents/backend/config.py` — patrón EXACTO default-ON (espejo de
   `STACKY_DEVOPS_PANEL_ENABLED` en `config.py:930-931`):
   ```python
   # ── Plan 130 — Verificador de integridad de código (default ON, decisión operador 2026-07-13, editable por UI) ──
   STACKY_CODE_INTEGRITY_ENABLED: bool = os.getenv(
       "STACKY_CODE_INTEGRITY_ENABLED", "true"
   ).strip().lower() == "true"
   ```
4. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp` (formato
   del dict, ver `STACKY_DOCS_GRAPH_ENABLED` en `harness_flags_help.py:268`):
   ```python
   "STACKY_CODE_INTEGRITY_ENABLED": PlainHelp(
       what="Verifica en segundos que TODO el código Python del backend compile (sintaxis) y que sus imports internos existan, sin ejecutar nada y sin IA.",
       on_effect="Si la activás: aparece la card 'Integridad del código' en Diagnóstico con el botón Verificar ahora, y el endpoint /api/diag/code-integrity responde. No corre solo: solo a demanda.",
       off_effect="Si la apagás: la card desaparece y el endpoint devuelve 404. El gate de 'Preparar Publicación' NO depende de esta flag (su bypass es -SkipCodeIntegrity).",
       example="Antes de publicar, el gate te dice 'api/devops_servers.py:223 — invalid syntax' en 2 segundos, en vez de un ModuleNotFoundError críptico tras minutos de build.",
   ),
   ```
5. `Stacky Agents/backend/harness_defaults.env` — **NO tocar, NO regenerar** (§3.7):
   sin línea `=false` para la key (test negativo).

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan130_code_integrity_flag.py`
(espejo EXACTO del F0 del Plan 127 y de la tanda default-ON 93-108,
`test_harness_flags.py:510`; 7 casos):
1. `test_flag_declarada_bool` — FlagSpec existe, `type == "bool"`, `group == "global"`.
2. `test_flag_default_true_en_spec` — `spec.default is True`.
3. `test_flag_ui_editable` — `spec.env_only` False y `spec.requires` None.
4. `test_flag_en_set_curado` — `from tests.test_harness_flags import _CURATED_DEFAULTS_ON`; key ∈ set.
5. `test_config_default_on` — con env limpio, `config.STACKY_CODE_INTEGRITY_ENABLED is True`
   (mismo mecanismo del assert de `STACKY_DEVOPS_PANEL_ENABLED`, `test_harness_flags.py:510`).
6. `test_categoria_capacidades_optin` — key ∈ `_CATEGORY_KEYS["capacidades_optin"]`.
7. `test_help_y_defaults_env_sin_linea_off` — help contiene la key Y
   `harness_defaults.env` NO contiene `STACKY_CODE_INTEGRITY_ENABLED=false`.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan130_code_integrity_flag.py tests/test_harness_flags.py -q`
**Criterio binario:** 7/7 verdes Y `test_harness_flags.py` sin regresión (fotografiar
fallos preexistentes ANTES de F0).
**Flag:** la propia. **Runtimes:** N/A. **Operador:** ninguno.

### F1 — Servicio puro: `services/code_integrity.py`

**Objetivo:** los 2 checks como funciones puras sobre `Path`, testeables con `tmp_path`.
**Valor:** el motor completo, congelado por tests, sin tocar app/ps1 todavía.

**Archivo a crear:** `Stacky Agents/backend/services/code_integrity.py`

**Símbolos EXACTOS (además de §4.1/§4.2/§4.3):**
```python
import ast
from pathlib import Path
from time import perf_counter

def backend_root() -> Path
def iter_py_files(root: Path) -> list[Path]        # §4.1, orden determinista (sorted)
def first_party_names(root: Path) -> set[str]      # §4.2
def resolve_module(root: Path, dotted: str) -> bool  # §4.2
def collect_exempt_linenos(tree: ast.AST) -> set[int]
    # linenos de imports dentro de ast.Try con handler que captura
    # ImportError/ModuleNotFoundError/Exception (§4.2, exención).
def check_file(root: Path, path: Path, first_party: set[str]) -> tuple[dict | None, list[dict]]
    # → (syntax_error | None, broken_imports). Parsea UNA vez con
    # ast.parse(text, filename=str(path)); SyntaxError/ValueError → (finding, []).
def run_checks(root: Path | None = None) -> dict   # ensambla §4.3 completo
```

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan130_code_integrity_service.py`
(todo con `tmp_path` salvo el caso 13; 13 casos):
1. `test_iter_py_files_exclusiones` — árbol con `.venv/x.py`, `__pycache__/y.py`,
   `data/z.py`, `api/ok.py` → solo `api/ok.py`; orden determinista.
2. `test_first_party_names` — raíz con `app.py`, `config.py`, `api/__init__.py`,
   `services/__init__.py`, dir `sueltos/` SIN `__init__.py` → exactamente
   `{"app", "config", "api", "services"}`.
3. `test_resolve_module` — `api.foo` con `api/foo.py` → True; `api.sub` con
   `api/sub/__init__.py` → True; `api.nada` → False.
4. `test_sintaxis_error_linea` — archivo con `def f(:` en línea 3 → finding
   `{"file": "api/roto.py", "line": 3, "message": <no vacío>}` (KPI-1, incidente 1).
5. `test_null_bytes` — archivo con `\x00` → finding con `line == 0`.
6. `test_import_absoluto_roto` — `import api.pr_reviewx` (api existe, el módulo no) →
   broken_imports con `import == "api.pr_reviewx"` y `line` correcto (KPI-1, incidente 2).
7. `test_from_import_modulo_ok_nombres_ignorados` — `from services import lo_que_sea`
   con `services/__init__.py` presente → 0 hallazgos.
8. `test_import_relativo` — en `api/__init__.py`, `from .foo import bp` sin `api/foo.py`
   → hallazgo; creando `api/foo.py` → 0.
9. `test_terceros_ignorados` — `import flask` + `from sqlalchemy import or_` → 0 hallazgos.
10. `test_exencion_try_import_error` — `try: import services.opcional\nexcept ImportError: pass`
    con el módulo inexistente → 0 hallazgos (exención §4.2); el MISMO import FUERA del
    try → 1 hallazgo.
11. `test_run_checks_shape_y_orden` — claves EXACTAS de §4.3; `ok` coherente;
    hallazgos ordenados (file ASC, line ASC); `files_scanned` correcto; `elapsed_ms` int ≥ 0.
12. `test_no_escribe_nada` — tras `run_checks` sobre el árbol tmp, `rglob("__pycache__")`
    y `rglob("*.pyc")` vacíos (guardarraíl §3.2).
13. `test_backend_real_sin_hallazgos` — `run_checks()` sobre el backend REAL → `ok is True`.
    Comentario OBLIGATORIO en el test: si falla, hay código Python roto DE VERDAD en el
    working tree (eso es el producto funcionando); mirar el reporte, no "arreglar" el test.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan130_code_integrity_service.py -q`
**Criterio binario:** 13/13 verdes.
**Flag:** no aplica (módulo puro). **Runtimes:** N/A. **Operador:** ninguno.

### F2 — CLI + endpoint: `scripts/check_code_integrity.py` + `GET /api/diag/code-integrity`

**Objetivo:** exponer el motor a la terminal (exit codes §4.4) y a la app (contrato §4.5).
**Valor:** usable a mano hoy mismo y consumible por el ps1 (F3) y la card (F4).

**Archivo a crear:** `Stacky Agents/backend/scripts/check_code_integrity.py`
```python
"""CLI del verificador de integridad (Plan 130). Exit: 0 ok, 1 hallazgos, 2 error interno."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ importable

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica sintaxis e imports del backend sin ejecutar codigo.")
    parser.add_argument("--root", default=None, help="Raiz a escanear (default: backend/)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        from services.code_integrity import run_checks
        report = run_checks(Path(args.root) if args.root else None)
    except Exception as exc:  # error interno del verificador, NUNCA del código analizado
        print(f"[code-integrity] error interno: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for f in report["syntax_errors"]:
            print(f"{f['file']}:{f['line']} — {f['message']}")
        for f in report["broken_imports"]:
            print(f"{f['file']}:{f['line']} — import roto: {f['import']}")
        total = len(report["syntax_errors"]) + len(report["broken_imports"])
        print(f"[code-integrity] {report['files_scanned']} archivos, {total} hallazgos, {report['elapsed_ms']} ms")
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
```

**Archivo a editar:** `Stacky Agents/backend/api/diag.py` — agregar al final (blueprint
`diag` YA registrado; url_prefix `/diag`, `api/diag.py:40`):
```python
@bp.get("/code-integrity")
def code_integrity_route():
    """Plan 130 — gate determinista de sintaxis + imports (read-only, sin IA)."""
    if not bool(getattr(_config.config, "STACKY_CODE_INTEGRITY_ENABLED", False)):
        return jsonify({"ok": False, "error": "code_integrity_disabled",
                        "message": "El verificador de integridad está deshabilitado (STACKY_CODE_INTEGRITY_ENABLED)."}), 404
    from services import code_integrity as ci  # import lazy (patrón Plan 109)
    try:
        return jsonify(ci.run_checks())
    except Exception as exc:
        return jsonify({"ok": False, "error": type(exc).__name__}), 200
```
`diag.py:26` YA tiene `import config as _config` (usado como `_config.config.X` en
`diag.py:364`, patrón Plan 106) — REUSAR ese alias tal cual, EXACTO como en el snippet de
arriba. PROHIBIDO declarar un import local nuevo con otro alias dentro de la función
(inconsistencia detectada en v1, corregida en v2).

**Tests PRIMERO:** `Stacky Agents/backend/tests/test_plan130_code_integrity_endpoint_cli.py`
(fixtures `app_flag_off`/`app_flag_on` COPIADAS de `tests/test_plan87_devops_endpoints.py:6-29`
cambiando el attr a `STACKY_CODE_INTEGRITY_ENABLED`; el CLI se testea IN-PROCESS importando
`main` — nada de subprocess; 7 casos):
1. `test_endpoint_404_flag_off` — 404 + `error == "code_integrity_disabled"`.
2. `test_endpoint_200_shape` — flag ON + `run_checks` monkeypatcheado → 200 con las 6
   claves de §4.3.
3. `test_endpoint_error_interno_sin_leak` — `run_checks` monkeypatcheado lanzando
   `RuntimeError("C:\\secreto")` → 200 `{"ok": False, "error": "RuntimeError"}` y
   "secreto" NO aparece en el body.
4. `test_ruta_sin_doble_prefijo` — url_map contiene `/api/diag/code-integrity` y NO
   `/api/api/diag/code-integrity`.
5. `test_cli_exit_0` — `main(["--root", str(tmp_ok)])` → 0.
6. `test_cli_exit_1_y_stdout` — árbol con un `def f(:` → 1 y stdout (capsys) contiene
   `roto.py:3`.
7. `test_cli_exit_2` — `run_checks` monkeypatcheado lanzando → 2.

**Comando:** `cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan130_code_integrity_endpoint_cli.py -q`
**Criterio binario:** 7/7 verdes.
**Flag:** gating 404 verificado. **Runtimes:** N/A. **Operador:** ninguno.

### F3 — Hook fail-fast en `Prepare-Publication.ps1`

**Objetivo:** que la publicación aborte en segundos ante código roto, ANTES de detener
procesos y buildear.
**Valor:** los 2 incidentes reales quedan estructuralmente imposibles de repetir.

**Archivo a editar:** `Stacky Agents/deployment/Prepare-Publication.ps1` (2 toques):
1. En el bloque `param(...)` (`:11-23`), agregar `[switch]$SkipCodeIntegrity,`
   inmediatamente después de la línea `[switch]$SkipSmokeTest,` (`:20`).
2. Insertar el bloque siguiente (ASCII, PS 5.1) INMEDIATAMENTE ANTES del primer
   `Write-Step` del flujo principal (la primera línea `Write-Step` FUERA de una
   `function`, después de las definiciones de helpers `:40-80`):
   ```powershell
   if (-not $SkipCodeIntegrity) {
       Write-Step "Verificando integridad del codigo backend (sintaxis + imports)"
       $backendDir = Join-Path $appRoot "backend"
       $ciPython = Join-Path $backendDir ".venv\Scripts\python.exe"
       if (-not (Test-Path $ciPython)) { $ciPython = "python" }
       $ciExit = 2
       try {
           & $ciPython (Join-Path $backendDir "scripts\check_code_integrity.py")
           $ciExit = $LASTEXITCODE
       } catch {
           $ciExit = 2
       }
       if ($ciExit -eq 1) {
           throw "Integridad de codigo FALLO: hay errores de sintaxis o imports rotos (detalle arriba). Corregilos antes de publicar o usa -SkipCodeIntegrity."
       }
       if ($ciExit -eq 2) {
           Write-Warn "El verificador de integridad no pudo correr; se continua (usa -SkipCodeIntegrity para silenciar)."
       } else {
           Write-OK "Codigo backend sin errores de sintaxis ni imports rotos"
       }
   }
   ```
   Semántica congelada (§4.4): exit 1 → `throw` (aborta ANTES de `Stop-DeployProcesses`);
   exit 2 o excepción de invocación → WARN y continuar; exit 0 → OK.

**Tests / verificación de fase (binaria, sin correr una publicación entera):**
- Greps de wiring (los 3 devuelven ≥1 match):
  `grep -n "SkipCodeIntegrity" "Stacky Agents/deployment/Prepare-Publication.ps1"` (param + bloque + mensajes);
  `grep -n "check_code_integrity.py" "Stacky Agents/deployment/Prepare-Publication.ps1"`;
  `grep -n "Integridad de codigo FALLO" "Stacky Agents/deployment/Prepare-Publication.ps1"`.
- Corrida REAL del CLI que el hook invoca (mismo comando):
  `cd "Stacky Agents/backend" && .venv\Scripts\python.exe scripts\check_code_integrity.py`
  → exit 0 sobre HEAD limpio (imprime el resumen).
- Sintaxis del ps1 verificable sin ejecutarlo:
  `powershell -NoProfile -Command "$null = [scriptblock]::Create((Get-Content -Raw 'Stacky Agents/deployment/Prepare-Publication.ps1'))"`
  → exit 0 (parsea sin error).
- La corrida completa de "Preparar Publicación" queda declarada como
  pendiente-de-operador (patrón disclosure Plan 111): es un flujo con efectos (backup,
  build, zip) que el operador dispara cuando publica de verdad.
**Criterio binario:** los 3 greps ≥1, CLI exit 0, parseo ps1 exit 0.
**Flag:** NO aplica al ps1 (§3.6 — su kill-switch es `-SkipCodeIntegrity`). **Runtimes:** N/A. **Operador:** ninguno (el hook corre solo dentro del flujo existente).

### F4 — Frontend: card "Integridad del código" en Diagnóstico (on-demand)

**Objetivo:** el operador corre el check con un botón y ve hallazgos copiables, sin abrir
una terminal.
**Valor:** diagnóstico en 1 click desde la página que ya usa para salud local.

**Archivos a crear (3):**
1. `Stacky Agents/frontend/src/diagnostics/codeIntegrityModel.ts` — modelo PURO
   (sin React; gotcha Plan 119: tests puros, sin RTL):
   ```typescript
   export interface CodeIntegrityFinding { file: string; line: number; message: string; import?: string; }
   export interface CodeIntegrityReport {
     ok: boolean; root?: string; files_scanned?: number; elapsed_ms?: number;
     syntax_errors?: CodeIntegrityFinding[]; broken_imports?: CodeIntegrityFinding[];
     error?: string;
   }
   export type CardView =
     | { kind: "ok"; summary: string }
     | { kind: "findings"; findings: CodeIntegrityFinding[]; summary: string; copyText: string }
     | { kind: "error"; message: string };

   export function fmtSummary(r: CodeIntegrityReport): string
     // `${files_scanned ?? 0} archivos en ${((elapsed_ms ?? 0) / 1000).toFixed(1)} s`

   export function reportToView(r: CodeIntegrityReport): CardView
     // r.error → {kind:"error", message:`El verificador falló (${r.error})`}
     // r.ok → {kind:"ok", summary: fmtSummary(r)}
     // si no → findings = [...syntax_errors ?? [], ...broken_imports ?? []] (sintaxis primero,
     //   cada lista en su orden), copyText = buildCopyText(r), summary = fmtSummary(r).

   export function buildCopyText(r: CodeIntegrityReport): string
     // una línea por hallazgo: `${file}:${line} — ${import ? "import roto: " + import : message}`
     // unidas con "\n". Listas ausentes = vacías.
   ```
2. `Stacky Agents/frontend/src/components/CodeIntegrityCard.tsx` — card con:
   fetch de montaje a `CodeIntegrity.get()` SOLO para decidir visibilidad (404/error →
   `return null`, la card no existe con flag OFF); estado `idle` con botón
   "Verificar ahora" (icono `ShieldCheck` de lucide-react, ya dependencia de la página);
   `running` (botón deshabilitado, texto "Verificando…"); resultado vía `reportToView`:
   `ok` → línea verde con `summary`; `findings` → lista `file:line — mensaje` en
   `<pre>` con scroll + botón "📋 Copiar hallazgos" (`navigator.clipboard.writeText(copyText)`
   en try/catch con "Copiado ✓" 1500 ms); `error` → texto ámbar. Estilos en
   `CodeIntegrityCard.module.css` (crear; clases `card`, `title`, `okLine`, `findings`,
   `copyBtn` — estética coherente con las cards vecinas).
3. `Stacky Agents/frontend/src/diagnostics/codeIntegrityModel.test.ts` (los 6 casos de abajo).

**Archivos a editar (2):**
1. `Stacky Agents/frontend/src/api/endpoints.ts` — namespace nuevo:
   ```typescript
   export const CodeIntegrity = {
     get: () =>
       fetch("/api/diag/code-integrity").then((r) => {
         if (!r.ok) throw new Error(`code integrity ${r.status}`);
         return r.json();
       }),
   };
   ```
2. `Stacky Agents/frontend/src/pages/DiagnosticsPage.tsx` — 2 toques: import de
   `CodeIntegrityCard` y montar `<CodeIntegrityCard />` INMEDIATAMENTE DESPUÉS de
   `<OperationalHealthCard />` (buscar por contenido; hoy está junto a
   `HarnessHealthCard`, imports en `DiagnosticsPage.tsx:13-14`).

**Tests PRIMERO:** `codeIntegrityModel.test.ts` (vitest puro; 6 casos):
1. `reportToView` con `ok:true` → kind "ok" y summary `"310 archivos en 1.2 s"` (fixture
   files_scanned 310, elapsed_ms 1240).
2. `reportToView` con hallazgos → kind "findings", sintaxis primero, orden preservado.
3. `reportToView` con `error` → kind "error" y el nombre de clase en el mensaje.
4. `buildCopyText` — mezcla sintaxis+imports → líneas exactas
   (`api/x.py:223 — invalid syntax`, `api/__init__.py:55 — import roto: api.pr_reviewx`).
5. Defensivo: listas ausentes (`syntax_errors`/`broken_imports` undefined) → vacías, sin throw.
6. `fmtSummary` con campos ausentes → `"0 archivos en 0.0 s"`.

**Comandos:**
`cd "Stacky Agents/frontend" && npx vitest run src/diagnostics/codeIntegrityModel.test.ts` y
`cd "Stacky Agents/frontend" && npx tsc --noEmit`
**Criterio binario:** 6/6 verdes; tsc exit 0; greps de wiring ≥1:
`grep -n "CodeIntegrity" "Stacky Agents/frontend/src/api/endpoints.ts"`,
`grep -n "CodeIntegrityCard" "Stacky Agents/frontend/src/pages/DiagnosticsPage.tsx"`.
**Flag:** OFF → fetch de montaje da 404 → card `null` (Diagnóstico queda idéntico a hoy).
**Runtimes:** idéntico en los 3. **Operador:** ninguno (on-demand).

### F5 — Cierre: ratchet + no-regresión + estado del doc

**Objetivo:** registrar los tests nuevos en el ratchet y dejar el plan auditable.

**Archivos a editar:**
1. `Stacky Agents/backend/scripts/run_harness_tests.ps1` y `.sh` — DOS cambios:
   a. Bloque nuevo dentro de `$HarnessTestFiles`/`HARNESS_TEST_FILES` con los 3 archivos
      `test_plan130_*.py` (un `pytest` por archivo, espejo de cualquier plan reciente).
   b. **[ADICIÓN ARQUITECTO]** Al INICIO del script, ANTES del `foreach ($f in
      $HarnessTestFiles)` (`.ps1`) / `for f in "${HarnessTestFiles[@]}"` (`.sh`), imprimir
      el resumen del CLI de integridad (F2) como chequeo INFORMATIVO previo — NO toca
      `$pass`/`$fail`/`exit` del ratchet (cero riesgo de romper su contrato de salida):
      ```powershell
      Write-Host "== Plan 130: integridad de codigo (informativo) =="
      & $python "scripts\check_code_integrity.py"
      Write-Host ""
      ```
      `.sh` equivalente: `echo "== Plan 130: integridad de codigo (informativo) =="`,
      `python3 scripts/check_code_integrity.py || true`, `echo`. Motivo: hoy, un
      `SyntaxError` en UN módulo compartido (p.ej. `api/devops_servers.py`, el incidente
      real del §2) hace que pytest falle la COLECCIÓN en decenas de archivos del ratchet a
      la vez, con tracebacks que ocultan la causa raíz — el mismo patrón
      "collect-submodules silencioso" pero en el loop de tests, no en PyInstaller. Este
      chequeo de 1-3s, impreso ANTES del loop, señala `file:line` real en segundos.
      Costo cero: reusa el CLI de F2, no requiere flag (el ratchet ya es una herramienta de
      desarrollador invocada a mano/CI, no un endpoint del operador), no cambia semántica
      de pass/fail existente.
2. Este doc: actualizar `**Estado:**` a `IMPLEMENTADO — <fecha> (F0..F5 …)` al cerrar.

**Verificación de la adición (binaria):**
`grep -n "check_code_integrity.py" "Stacky Agents/backend/scripts/run_harness_tests.ps1" "Stacky Agents/backend/scripts/run_harness_tests.sh"`
→ ambos ≥1 match (además de los 3 `test_plan130_*.py` ya exigidos).

**Comandos de cierre (todos verdes, por archivo):**
```
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan130_code_integrity_flag.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan130_code_integrity_service.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_plan130_code_integrity_endpoint_cli.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
cd "Stacky Agents/backend" && .venv\Scripts\python.exe scripts\check_code_integrity.py
cd "Stacky Agents/frontend" && npx vitest run src/diagnostics/codeIntegrityModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio binario:** los 7 comandos verdes (única excepción: fallos preexistentes de
`test_harness_flags.py` fotografiados antes de F0, conteo idéntico).
**Runtimes:** N/A. **Operador:** ninguno.

---

## 6. Riesgos y mitigaciones

- **R1 — Falsos positivos por imports condicionales/opcionales:** solo se valida la
  EXISTENCIA del módulo (nunca nombres/atributos) y los imports dentro de
  `try/except ImportError|ModuleNotFoundError|Exception` están exentos (§4.2, test F1
  caso 10). KPI-2 exige 0 hallazgos sobre el backend real ANTES de mergear.
- **R2 — El test integrador (F1 caso 13) se pone rojo por WIP ajeno roto:** eso es señal
  REAL (el producto detectando código roto en el working tree), no flakiness — el
  comentario obligatorio del test lo deja escrito. Reportar el hallazgo, no tocar el test.
- **R3 — PS 5.1 / encoding:** bloque del hook en ASCII puro, sin `&&`, `throw` bajo
  `$ErrorActionPreference = "Stop"` (patrón del propio script); verificación por parseo
  de scriptblock (F3) sin ejecutar la publicación.
- **R4 — Performance:** `ast.parse` de ~310 archivos corre en ~1-3 s local; `elapsed_ms`
  queda en el payload para vigilarlo. Sin caché (cada corrida es sobre el árbol vivo; un
  caché podría mentir justo antes de publicar).
- **R5 — Meta-tests de flags con default ON:** patrón triple §3.6 del Plan 127 + test
  negativo de `harness_defaults.env` (F0 caso 7).
- **R6 — Colisión de numeración (loop paralelo ACTIVO):** verificar `130_*` único antes
  del commit del doc y de nuevo al implementar (§3.10).
- **R7 — Divergencia futura con el Plan 102:** cuando el orquestador exista, el gate se
  enchufa a su `beforeCommit` (veto) SIN cambios en el motor — el contrato §4.3/§4.4 ya
  es apto; queda declarado como integración futura (§7), no dependencia.
- **R8 — Deploy congelado (PyInstaller):** el endpoint corre sobre el árbol del deploy
  (fuentes empaquetadas pueden no existir como `.py`); `run_checks` sobre una raíz sin
  `.py` devuelve `ok: true, files_scanned: 0` — inocuo. El valor principal del gate está
  en la máquina de desarrollo (donde se publica), que siempre tiene fuentes.

## 7. Fuera de scope (explícito)

- Typecheck del frontend en el gate (`frontend\dist` llega precompilado a la publicación
  — `Prepare-Publication.ps1:306`; sumar `tsc` sería otro plan).
- Validar NOMBRES importados (`from x import y` con `y` inexistente) — indecidible
  estáticamente sin importar; el smoke post-build existente sigue cubriendo el resto.
- Verificar dependencias de terceros (requirements/venv) — es entorno, no código.
- Integración con el orquestador del Plan 102 (`beforeCommit`) — enganche futuro declarado.
- Cualquier autocorrección (formatear, arreglar imports) — HITL: el gate informa y bloquea.
- IA/modelo local (el doctor narrativo es el Plan 127-C3).
- Auth/RBAC/multiusuario.

## 8. Glosario (para modelos menores)

- **Gate:** chequeo que puede ABORTAR un flujo (acá: la publicación) con evidencia.
- **`ast.parse` vs importar:** parsear construye el árbol sintáctico SIN ejecutar el
  módulo (importar SÍ ejecuta side effects). Por eso el verificador es 100% inocuo.
- **Primera parte:** módulos/paquetes que viven en `backend/` (api, services, config, …),
  a diferencia de terceros instalados en el venv (flask, sqlalchemy).
- **Fail-closed / fail-open:** ante CÓDIGO roto el gate bloquea (closed); ante ENTORNO
  roto (sin python/venv) avisa y deja seguir (open) — bloquear por entorno castigaría al
  operador sin motivo.
- **Preparar Publicación:** `deployment/Prepare-Publication.ps1` — script PowerShell que
  buildea el release (PyInstaller), respalda el deploy anterior y arma el zip.
- **Smoke test del release:** pytest post-build (`build_release.ps1:703-719`) que valida
  el ejecutable congelado; hoy es la ÚNICA red y llega tarde.
- **Gotcha collect-submodules:** PyInstaller omite en silencio submódulos con
  `SyntaxError`; el síntoma visible es un `ModuleNotFoundError` engañoso en el smoke.
- **Flag del arnés / patrón triple default ON:** ver Plan 127 §3.6 — FlagSpec
  `default=True` + key curada en `_CURATED_DEFAULTS_ON` + `config.py` con `"true"`.
- **HITL (human-in-the-loop):** el operador decide (puede saltear el gate); Stacky
  informa y bloquea por defecto con evidencia.
- **3 runtimes:** Codex CLI, Claude Code CLI y GitHub Copilot Pro. Este plan no invoca
  ninguno: es tooling local determinista.
- **venv del repo:** `Stacky Agents/backend/.venv` (Python 3.13); tests con
  `.venv\Scripts\python.exe -m pytest`, por archivo.
- **Ratchet:** `scripts/run_harness_tests.ps1/.sh` — suites acumulativas que deben
  quedar verdes; cada plan registra las suyas.
- **Staging quirúrgico:** commitear solo hunks/archivos propios; prohibido
  stash/reset/checkout con WIP ajeno.

## 9. Orden de implementación

1. F0 (flag triple ON + config + help + curado) — fotografiar `test_harness_flags.py` ANTES.
2. F1 (servicio puro; 13 tests — incluye el integrador sobre el backend real).
3. F2 (CLI + endpoint; 7 tests).
4. F3 (hook ps1 + greps + parseo + CLI real exit 0).
5. F4 (modelo TS + card + endpoints.ts + DiagnosticsPage + tsc; 6 tests).
6. F5 (ratchet + estado del doc + corrida completa de cierre).

## 10. Definición de Hecho (DoD)

- [ ] `STACKY_CODE_INTEGRITY_ENABLED` declarada con patrón triple default ON, UI-editable,
      categoría `capacidades_optin`, help presente, `harness_defaults.env` sin línea `=false`.
- [ ] Los 3 archivos de test backend verdes con los comandos EXACTOS de §5
      (27 casos: 7+13+7).
- [ ] `codeIntegrityModel.test.ts` verde (6) y `npx tsc --noEmit` exit 0.
- [ ] CLI real sobre HEAD limpio: exit 0 con resumen impreso (KPI-2).
- [ ] Fixtures de los 2 incidentes detectados con archivo:línea exactos (KPI-1).
- [ ] Hook en `Prepare-Publication.ps1`: 3 greps ≥1, parseo scriptblock exit 0,
      `-SkipCodeIntegrity` presente en `param(...)`; con el switch, flujo idéntico a hoy (KPI-4).
- [ ] Con flag OFF: endpoint 404 `code_integrity_disabled` y card ausente de Diagnóstico.
- [ ] El servicio no ejecuta ni escribe: `grep -n "subprocess\|py_compile\|compileall\|importlib\|exec(\|eval(" "Stacky Agents/backend/services/code_integrity.py"` → 0 matches;
      test F1 caso 12 (sin `__pycache__`/`.pyc`) verde.
- [ ] `App.tsx` SIN cambios (`git diff --name-only` no lo incluye).
- [ ] Ratchet ps1/sh actualizados con los 3 `test_plan130_*` Y con el chequeo informativo
      `check_code_integrity.py` al inicio ([ADICIÓN ARQUITECTO] F5), sin alterar el
      contrato de exit code del ratchet.
- [ ] `**Estado:**` de este doc actualizado al cerrar.
- [ ] `git status` final: WIP ajeno intacto (staging quirúrgico verificado).
