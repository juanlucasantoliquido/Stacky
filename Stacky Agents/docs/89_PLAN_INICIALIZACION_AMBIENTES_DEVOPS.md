# Plan 89 — Inicialización de ambientes desde el panel DevOps

**Estado:** PROPUESTO
**Fecha:** 2026-07-03
**Serie DevOps:** plan 3 de 3 (CIERRE de la serie).
**Dependencias:** plan 88 (`88_PLAN_PUBLICACIONES_PARAMETRIZABLES_PROCESOS_DEVOPS.md`,
commit `a001e544` — publicaciones; provee la "publicación inicial TODO"), que a su vez
depende del plan 87 (`87_PLAN_PANEL_DEVOPS_CREADOR_GRAFICO_PIPELINES.md`, commit
`59918622` — panel DevOps base). Además, planes 45/71/72/73 implementados — VERIFICADO:

| Pieza reusada | Origen |
|---|---|
| `DevOpsPage` + `DEVOPS_SECTIONS` (agregar sección = 1 entrada + 1 componente) | plan 87 F4 |
| Blueprint `backend/api/devops.py` + health con booleans por sub-feature | plan 87 F1 / 88 F3 |
| Materializador puro `build_publication_spec` (`services/publication_spec.py`) | plan 88 F1 |
| Modelo en client_profile: `devops_publication_presets`, `devops_publication_settings`, `publish_group` | plan 88 §4 |
| `ALLOWED_PROCESS_KINDS = {"entry","processing","output"}` | `backend/api/client_profile.py:57` |
| Preview/commit YAML HITL | `backend/api/pipeline_generator.py:34,52,59-60` (plan 73) |
| Trigger/monitor CI HITL | `backend/api/ci.py:26,76,139,174` (plan 72) |
| PUT client_profile con validación aditiva por key | `backend/api/client_profile.py:127,138-156` (plan 45) |

> **Nota de secuencia:** implementar 87 → 88 → 89. Las fases F0-F2 de este plan no
> tocan código de 87/88 y pueden adelantarse; F3-F5 requieren 87 F1/F4 y 88 F1/F3.

---

## 1. Objetivo + KPI

Inicializar un **ambiente nuevo** desde el panel DevOps en dos partes: **(a)** crear el
**sistema de carpetas** que los procesos del cliente necesitan — estructura DERIVADA
del process_catalog parametrizado (jamás hardcodeada): en Pacífico, las carpetas de
entrada `IN_` (donde deja Mul2Bane), `productivas` (donde pasa IncHost / aplica RSCore)
y `salida` (donde genera RsExtrae) — con mapeo `kind → subcarpetas` parametrizable por
UI; y **(b)** disparar la **publicación inicial** de lo parametrizado como "TODO",
reusando el materializador del plan 88 SIN duplicar una línea. Regla de oro:
**IDEMPOTENTE Y NUNCA DESTRUCTIVO** — re-inicializar un ambiente existente detecta y
reporta, jamás borra ni sobrescribe (plan-then-apply con HITL).

**KPI / impacto esperado:**
- Ambiente nuevo operativo (carpetas + publicación inicial previewada) en < 5 minutos
  desde la UI, 0 comandos manuales de mkdir, 0 YAML a mano.
- Re-inicializar un ambiente ya inicializado ⇒ **0 cambios en disco** (todo
  `exists_ok`) con reporte visible — criterio binario F2.
- Cero caminos de código capaces de borrar: verificado por test centinela
  anti-destrucción (F2).

## 2. Por qué ahora / gap que cierra

Con 87 (crear pipelines gráficamente) y 88 (publicar procesos parametrizados) el panel
DevOps cubre el día 2 en adelante. El día 0 — montar un ambiente nuevo: carpetas del
flujo batch + primera publicación completa — sigue siendo manual, propenso a error
(carpeta faltante ⇒ el batch falla en runtime) y sin trazabilidad. Este plan cierra la
serie: el catálogo de procesos (plan 45) ya sabe QUÉ existe y de QUÉ kind es; de ahí se
DERIVA el layout de carpetas, y la publicación inicial es literalmente el preset TODO
del plan 88. Todo el conocimiento ya está en Stacky; solo falta el ejecutor no
destructivo.

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop en dos escalones:** primero el operador VE el plan de carpetas
   (dry-run puro, endpoint de PLAN solo-lectura); recién con confirmación explícita
   (`confirm:true`) se aplica SOLO lo aprobado. La publicación inicial pasa por los
   MISMOS HITL de los planes 88/73/72 (materializar solo-lectura → commit con checkbox
   → trigger con preview).
2. **Nunca destructivo:** ningún camino de código de este plan borra ni sobrescribe
   NADA. Prohibidos `shutil.rmtree`, `os.rmdir`, `os.remove`, `os.unlink`,
   `os.replace`, `shutil.move` y toda escritura de archivos en el módulo de
   inicialización. Hay test centinela que lo verifica sobre el código fuente (F2).
   `conflict` (existe un ARCHIVO donde va una carpeta) se REPORTA, jamás se toca.
3. **Dónde se crean las carpetas — decisión justificada:** en la **máquina del
   operador** (filesystem local del backend). Justificación: Stacky es mono-operador y
   el backend corre local en esa máquina (riel del sistema); los ambientes
   batch del dominio son rutas de disco visibles para el operador. La raíz es
   parametrizada por el operador (`environment_root`), validada: **ruta absoluta** y
   **NO raíz de disco** (ni `C:\` ni `/`).
4. **Anti path-traversal:** toda ruta final se construye
   `os.path.join(root, relativa)` y ANTES de crear se verifica
   `os.path.commonpath([root, final]) == root`. Los nombres de proceso se sanitizan a
   slug (mismo regex `[^a-zA-Z0-9._-]+ → "-"` de `api/pipeline_generator.py:27-31`)
   ANTES de formar rutas — un catálogo con `name="../../evil"` no puede escapar de root.
5. **Flag propia** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`: `FLAG_REGISTRY` con
   `requires="STACKY_DEVOPS_PANEL_ENABLED"` (nota: `requires` acepta UNA key bool,
   plan 82 `harness_flags.py:30` — la dependencia funcional del plan 88 se declara acá
   y en la UI por mensaje, NO en `requires`), categoría `devops`, `env_only=False` ⇒
   alta en `config.py` (gotcha plan 81), **SIN `default=`** (gotcha
   `_CURATED_DEFAULTS_ON`), **con `PlainHelp`** (meta-test plan 86).
6. **Byte-idéntico con flag OFF:** endpoints nuevos 404, sección UI ausente,
   validaciones aditivas inertes.
7. **Mono-operador sin auth. No degradar:** contratos 45/71/72/73/87/88 intactos;
   todo aditivo. **Ratchet:** tests nuevos registrados en
   `backend/scripts/run_harness_tests.{sh,ps1}`.
8. **3 runtimes (Codex/Claude/Copilot):** no toca el camino de agentes; impacto
   NINGUNO en los tres (se declara por fase).

## 4. Modelo de datos (contrato, consumido por F1-F5)

Key NUEVA en client_profile (patrón plan 45/87/88):

```json
"devops_environment_settings": {
  "environment_root": "C:\\ambientes\\pacifico",   // absoluta, NO raíz de disco
  "folder_layout": {                                 // kind → subcarpetas relativas
    "entry":      ["IN_"],
    "processing": ["productivas"],
    "output":     ["salida"],
    "default":    []                                  // kinds desconocidos/ausentes
  },
  "per_process_subfolder": false                     // true ⇒ además <carpeta>/<slug-proceso>
}
```

**Semántica del layout (F1, determinista):**
- Para cada entrada del catálogo con kind `k`: aporta las carpetas de
  `folder_layout[k]` (si `k` no está en el layout ⇒ `folder_layout["default"]`).
- Si `per_process_subfolder == true`: además aporta `carpeta/<slug(name)>` por cada
  proceso (slug del §3.4; entradas sin `name` string no vacío se ignoran).
- Resultado: lista de rutas RELATIVAS, únicas (dedup), ordenadas (`sorted`), sin
  separador inicial/final. Segmentos inválidos en el layout (vacíos, `..`, absolutos,
  con `:`) NO llegan acá: los rechaza la validación F3 al guardar; el builder además
  los OMITE defensivamente (nunca lanza).
- Catálogo vacío o layout todo vacío ⇒ lista vacía (el plan resultante reporta 0
  entradas; la UI lo muestra, no es error).

**Estados del plan de carpetas (F2):** para cada ruta relativa `p` con final
`f = join(root, p)`:
- `to_create` — `f` no existe.
- `exists_ok` — `f` existe y es directorio.
- `conflict` — `f` existe y NO es directorio (archivo/symlink): se reporta, NUNCA se toca.
- `unsafe` — falló el check de `commonpath` (§3.4): se reporta, NUNCA se crea.

## 5. Fases

> Comandos de test: idénticos a planes 87/88 (pytest por archivo con
> `backend/.venv/Scripts/python.exe` desde `Stacky Agents/backend`; frontend
> `npx tsc --noEmit` + `npx vitest run <archivo>`, solo TS puro).

### F0 — Flag `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`

**Objetivo:** alta de la flag en las 4 patas (misma mecánica que 87 F0 / 88 F0).

**Archivos a editar:**
1. `Stacky Agents/backend/config.py` — junto a las flags devops de 87/88:
   ```python
   STACKY_DEVOPS_ENVIRONMENTS_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", "false"
   ).strip().lower() == "true"
   ```
2. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CATEGORY_KEYS["devops"]` += `"STACKY_DEVOPS_ENVIRONMENTS_ENABLED",  # Plan 89 — inicialización de ambientes`.
   - `FlagSpec(key="STACKY_DEVOPS_ENVIRONMENTS_ENABLED", type="bool",
     description="Seccion Ambientes del panel DevOps: crea el arbol de carpetas del ambiente (plan-then-apply, nunca borra) y lanza la publicacion inicial.",
     env_only=False, requires="STACKY_DEVOPS_PANEL_ENABLED")` — ⚠️ SIN `default=`,
     SIN `reserved=`.
3. `Stacky Agents/backend/services/harness_flags_help.py` — entrada `PlainHelp`
   (modelo: la de `STACKY_PIPELINE_GENERATOR_ENABLED`, línea 595; mencionar en llano:
   "solo crea carpetas nuevas, nunca borra nada").

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environments_flag.py`:
- `test_f0_flag_in_registry` (`env_only is False`,
  `requires == "STACKY_DEVOPS_PANEL_ENABLED"`), `test_f0_flag_in_category_devops`,
  `test_f0_config_default_off`, `test_f0_flag_has_plain_help`.
- No-regresión: `tests/test_harness_flags.py` + `tests/test_flag_wiring.py`.

**Ratchet:** registrar el archivo. **Criterio binario:** 4+2 verdes; default OFF.
**Flag:** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (default OFF).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno (opt-in).

### F1 — Layout PURO: `build_environment_layout` (catálogo → rutas relativas)

**Objetivo:** derivar determinísticamente el árbol de carpetas del catálogo, sin I/O.

**Archivo NUEVO:** `Stacky Agents/backend/services/environment_init.py`
```python
"""environment_init.py — Plan 89. Inicialización de ambientes.
build_environment_layout: PURO (sin I/O). plan_environment: solo LECTURA de FS.
apply_environment: SOLO os.makedirs (nunca borra; ver test centinela F2)."""
import os
import re

_LAYOUT_KINDS = ("entry", "processing", "output", "default")

def _slug(name: str) -> str:
    """Mismo regex que api/pipeline_generator.py:27-31 (copiado, no importado)."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower()).strip("-")
    return s or "proceso"

def _safe_segment(seg: str) -> bool:
    """Relativo, sin '..', sin ':', sin separador inicial, no vacío."""
    seg = (seg or "").strip()
    return bool(seg) and ".." not in seg and ":" not in seg \
        and not seg.startswith(("/", "\\")) and not os.path.isabs(seg)

def build_environment_layout(catalog: list[dict], settings: dict | None) -> list[str]:
    """Rutas RELATIVAS únicas y ordenadas según §4. Nunca lanza; omite lo inválido.
    settings None o sin folder_layout -> []. Separador interno SIEMPRE '/'."""
```
(Implementación: iterar catálogo; por entrada tomar
`folder_layout.get(kind, folder_layout.get("default", []))`; filtrar con
`_safe_segment`; si `per_process_subfolder` ⇒ agregar `f"{seg}/{_slug(name)}"`;
`return sorted(set(acc))`.)

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environment_layout.py`
(reusar el `_CATALOG` de 6 entradas del plan 88 F1 como fixture local + settings §4):
- `test_f1_pacifico_layout_basic`: settings §4 con `per_process_subfolder=false` ⇒
  `["IN_", "productivas", "salida"]` (orden `sorted`, dedup aunque haya 2 processing).
- `test_f1_per_process_subfolders`: `per_process_subfolder=true` ⇒ incluye
  `"IN_/mul2bane"`, `"productivas/inchost"`, `"productivas/rscore"`,
  `"salida/rsextrae"` además de las 3 bases.
- `test_f1_unknown_kind_uses_default`: entrada `kind="zzz"` con
  `default=["misc"]` ⇒ aporta `"misc"`.
- `test_f1_empty_settings_empty`: settings `None` ⇒ `[]`; `folder_layout` ausente ⇒ `[]`.
- `test_f1_unsafe_segments_omitted`: layout con `["../fuga", "C:\\abs", "ok"]` ⇒ solo
  `"ok"` aparece.
- `test_f1_traversal_process_name_sanitized`: entrada
  `name="../../evil"`, `per_process_subfolder=true` ⇒ el slug resultante NO contiene
  `".."` ni `"/"` extra (queda `"IN_/evil"` o el slug saneado; assert:
  ningún path del resultado contiene `".."`).
- `test_f1_deterministic_and_pure`: dos llamadas con los mismos argumentos devuelven
  listas iguales; catálogo y settings de entrada no mutados (deepcopy previo).

**Ratchet:** registrar. **Criterio binario:** 7 tests verdes.
**Flag:** ninguna (puro, sin consumidores hasta F4). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F2 — Plan-then-apply NO destructivo (`plan_environment` / `apply_environment`)

**Objetivo:** clasificar rutas (dry-run) y crear SOLO lo aprobado, sin capacidad
técnica de borrar.

**Archivo a editar:** `Stacky Agents/backend/services/environment_init.py` (agregar):
```python
def validate_root(root: str) -> str | None:
    """None si OK; mensaje de error si no. Reglas: string no vacío, os.path.isabs,
    y NO raíz de disco: normpath(root) != normpath(splitdrive(root)[0] + os.sep)
    (cubre 'C:\\' en Windows y '/' en POSIX)."""

def plan_environment(root: str, rel_paths: list[str]) -> dict:
    """SOLO LECTURA. Retorna:
    {'root': root, 'entries': [{'path': rel, 'status': 'to_create'|'exists_ok'|'conflict'|'unsafe'}],
     'summary': {'to_create': n, 'exists_ok': n, 'conflict': n, 'unsafe': n}}
    Por cada rel: final = os.path.abspath(os.path.join(root, rel));
    'unsafe' si os.path.commonpath([os.path.abspath(root), final]) != os.path.abspath(root)
    (o si commonpath lanza ValueError — drives distintos en Windows);
    'to_create' si not os.path.exists(final); 'exists_ok' si os.path.isdir(final);
    'conflict' en el resto (existe y no es dir)."""

def apply_environment(root: str, rel_paths: list[str]) -> dict:
    """CREA SOLO to_create. Re-planifica server-side (plan_environment) y aplica
    os.makedirs(final, exist_ok=True) ÚNICAMENTE a la intersección
    rel_paths ∩ to_create (nunca confía en la lista del cliente).
    Retorna {'created': [rel...], 'skipped_existing': [...], 'conflicts': [...],
    'unsafe': [...]}. Los conflict/unsafe JAMÁS se tocan. NUNCA borra nada."""
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environment_plan_apply.py`
(usar `tmp_path` de pytest como root real):
- `test_f2_validate_root_rules`: `""` ⇒ error; relativa ⇒ error; raíz de disco
  (`os.path.splitdrive(str(tmp_path))[0] + os.sep` en Windows, `"/"` en POSIX) ⇒
  error; `tmp_path` ⇒ None.
- `test_f2_plan_fresh_all_to_create`: root vacío + 3 rutas ⇒ 3 `to_create`.
- `test_f2_plan_existing_dir_exists_ok`: pre-crear `IN_` ⇒ `exists_ok`.
- `test_f2_plan_file_conflict`: pre-crear ARCHIVO llamado `salida` ⇒ `conflict`.
- `test_f2_plan_unsafe_traversal`: rel `"../fuera"` ⇒ `unsafe` (y NO aparece nunca en
  to_create).
- `test_f2_apply_creates_only_to_create`: aplicar ⇒ dirs creados; el archivo
  `salida` sigue INTACTO byte a byte (leer contenido antes/después).
- `test_f2_apply_idempotent_second_run_zero`: aplicar 2 veces ⇒ segunda vez
  `created == []` y plan posterior todo `exists_ok` (criterio de idempotencia del
  plan).
- `test_f2_apply_ignores_client_paths_not_in_plan`: pedir aplicar `"../fuera"` y una
  ruta inexistente en el layout ⇒ nada creado fuera de root (verificar que
  `tmp_path.parent` no ganó entradas nuevas).
- `test_f2_source_has_no_destructive_calls` (CENTINELA anti-destrucción): leer el
  texto de `services/environment_init.py` y assert que NO contiene ninguno de:
  `"rmtree"`, `"rmdir"`, `"unlink"`, `"os.remove"`, `"os.replace"`, `"shutil.move"`,
  `"open("` (el módulo no escribe archivos, solo crea directorios).

**Ratchet:** registrar. **Criterio binario:** 9 tests verdes.
**Flag:** ninguna (sin consumidores hasta F4). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Validación aditiva de `devops_environment_settings` en client_profile

**Objetivo:** persistencia segura por UI del root y el layout.

**Archivo a editar:** `Stacky Agents/backend/api/client_profile.py` — después del
bloque del plan 88 F2, mismo patrón aditivo (key ausente = no-op):
```python
# Plan 89 F3 — settings de ambiente (aditivo).
env_settings = profile.get("devops_environment_settings")
if env_settings is not None:
    if not isinstance(env_settings, dict):
        return jsonify({"ok": False, "error": "devops_environment_settings debe ser un objeto."}), 400
    root = env_settings.get("environment_root")
    if root is not None:
        from services.environment_init import validate_root
        err = validate_root(root)
        if err:
            return jsonify({"ok": False, "error": f"environment_root: {err}"}), 400
    layout = env_settings.get("folder_layout")
    if layout is not None:
        from services.environment_init import _safe_segment
        if not isinstance(layout, dict) or any(k not in ("entry", "processing", "output", "default") for k in layout):
            return jsonify({"ok": False, "error": "folder_layout: keys en {entry,processing,output,default}."}), 400
        for k, segs in layout.items():
            if not isinstance(segs, list) or any(not isinstance(s, str) or not _safe_segment(s) for s in segs):
                return jsonify({"ok": False, "error": f"folder_layout.{k}: lista de rutas relativas seguras (sin '..', sin ':', no absolutas)."}), 400
    pps = env_settings.get("per_process_subfolder")
    if pps is not None and not isinstance(pps, bool):
        return jsonify({"ok": False, "error": "per_process_subfolder debe ser booleano."}), 400
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_env_settings_validation.py`:
- `test_f3_absent_key_noop` (PUT sin la key ⇒ 200).
- `test_f3_root_relative_400`, `test_f3_root_drive_root_400`,
  `test_f3_layout_bad_key_400`, `test_f3_layout_traversal_segment_400`
  (`{"entry": ["../x"]}` ⇒ 400), `test_f3_pps_not_bool_400`.
- `test_f3_valid_roundtrip`: PUT con settings §4 (root = un `tmp_path` real) ⇒ 200 y
  GET los devuelve intactos.

**Ratchet:** registrar. **Criterio binario:** 7 tests verdes + tests de client_profile
de planes 45/87/88 verdes.
**Flag:** ninguna (aditivo inerte). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F4 — Endpoints `POST /api/devops/environments/plan` y `/apply`

**Objetivo:** exponer plan-then-apply con datos reales del proyecto, HITL server-side.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` (del plan 87 F1; imports:
`from services.environment_init import build_environment_layout, plan_environment,
apply_environment, validate_root` + el mismo loader de client_profile del plan 88 F3):
```python
def _load_env_context(body):
    """Helper compartido plan/apply. Retorna (root, rel_paths) o (None, respuesta_error)."""
    project = body.get("project")
    if not project:
        return None, (jsonify({"error": "project es obligatorio"}), 400)
    profile = load_client_profile(project) or {}
    settings = profile.get("devops_environment_settings") or {}
    root = settings.get("environment_root")
    err = validate_root(root or "")
    if err:
        return None, (jsonify({"error": f"environment_root invalido o no configurado: {err}",
                               "kind": "environment_root_invalid"}), 400)
    rel_paths = build_environment_layout(profile.get("process_catalog") or [], settings)
    return (root, rel_paths), None

@bp.post("/environments/plan")
def environment_plan_route():
    """Dry-run SOLO-LECTURA del árbol de carpetas."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    ctx, err = _load_env_context(request.get_json(silent=True) or {})
    if err: return err
    root, rel_paths = ctx
    return jsonify(plan_environment(root, rel_paths))

@bp.post("/environments/apply")
def environment_apply_route():
    """Crea SOLO to_create. HITL: confirm=True obligatorio (patrón pipeline_generator.py:59-60)."""
    if not getattr(_config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400
    ctx, err = _load_env_context(body)
    if err: return err
    root, rel_paths = ctx
    requested = body.get("paths")
    if not isinstance(requested, list) or not requested:
        return jsonify({"error": "paths (lista no vacia) es obligatorio"}), 400
    # server-side: solo la intersección con el layout derivado del catálogo REAL
    return jsonify(apply_environment(root, [p for p in rel_paths if p in set(requested)]))
```
Además, en `devops_health_route`: agregar
`"environments_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", False))`
(aditivo).
**La publicación inicial NO necesita backend nuevo:** el frontend (F5) reusa
`POST /api/devops/publications/materialize` (plan 88 F3) + preview/commit (plan 73) +
trigger (plan 72).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan89_environments_endpoints.py`
(fixtures flag on/off sobre `STACKY_DEVOPS_ENVIRONMENTS_ENABLED`, patrón
`test_plan73_generator_endpoint.py:8-31`; mock del loader de client_profile en el
módulo `api.devops`; root = `tmp_path`):
- `test_f4_plan_flag_off_404`, `test_f4_apply_flag_off_404`.
- `test_f4_plan_no_root_400`: profile sin `environment_root` ⇒ 400 con
  `kind == "environment_root_invalid"`.
- `test_f4_plan_ok`: profile con catálogo Pacífico + settings §4 ⇒ 200, 3 entries
  `to_create`.
- `test_f4_apply_without_confirm_400`: `confirm` ausente o `false` ⇒ 400 (HITL).
- `test_f4_apply_creates_and_reports`: confirm + paths = los 3 ⇒ 200, `created` == 3,
  dirs existen bajo `tmp_path`.
- `test_f4_apply_path_not_in_layout_ignored`: paths con `"../evil"` ⇒ 200 y `created`
  NO lo incluye; nada fuera de root.
- `test_f4_rerun_idempotent`: segundo apply ⇒ `created == []`; segundo plan ⇒ todo
  `exists_ok`.
- `test_f4_health_exposes_environments_enabled`.

**Ratchet:** registrar. **Criterio binario:** 9 tests verdes + tests plan 87 F1 /
88 F3 verdes (health sigue compatible).
**Flag:** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (guard per-request en ambos endpoints).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F5 — Frontend: sección "Ambientes" (wizard de 2 pasos)

**Objetivo:** UI del flujo completo: configurar → plan → aplicar → publicación inicial.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/environmentModel.ts` (TS puro):
- Tipos espejo §4 (`EnvironmentSettings`, `folder_layout` con keys
  `entry|processing|output|default`, `PlanEntry {path, status}` con
  `status: "to_create"|"exists_ok"|"conflict"|"unsafe"`).
- Funciones puras: `emptyEnvironmentSettings()` (layout Pacífico §4 como default de
  UI: entry→IN_, processing→productivas, output→salida — SOLO como sugerencia inicial
  editable, no hardcode de backend); `validateSettingsLocal(s): string[]` (espejo de
  F3: root no vacío/absoluto-a-simple-vista `/^[A-Za-z]:[\\/]|^\//`, segmentos sin
  `..`/`:`); `summarizePlan(entries): {to_create, exists_ok, conflict, unsafe}`;
  `selectablePaths(entries): string[]` (solo `to_create`).

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx`:
- **Paso 0 — Configuración:** editor de `devops_environment_settings` (input root,
  3+1 listas de segmentos por kind, toggle per_process_subfolder), persiste vía PUT
  client-profile (patrón presets plan 88 F5). Si health da
  `environments_enabled:false` ⇒ mensaje "Activá STACKY_DEVOPS_ENVIRONMENTS_ENABLED
  (Configuración → Arnés, categoría DevOps)" (patrón MigratorPage.tsx:35-47). Si
  `publications_enabled:false` ⇒ banner: "La publicación inicial requiere además
  STACKY_DEVOPS_PUBLICATIONS_ENABLED (plan 88)" (dependencia declarada por mensaje,
  no por `requires`).
- **Paso 1 — Carpetas (plan-then-apply):** botón "Calcular plan" ⇒
  `DevOps.environmentPlan(project)` ⇒ tabla de entries con color por status
  (to_create verde, exists_ok gris, conflict rojo con leyenda "existe un archivo con
  ese nombre; Stacky NUNCA lo toca", unsafe rojo). Checkbox HITL "Confirmo crear las
  N carpetas nuevas" ⇒ habilita botón "Crear carpetas" ⇒
  `DevOps.environmentApply(project, selectablePaths(entries))` (con `confirm:true`) ⇒
  reporte created/skipped/conflicts. Re-correr sobre ambiente inicializado muestra
  "0 cambios — ambiente ya inicializado".
- **Paso 2 — Publicación inicial (TODO):** selector de preset (los
  `devops_publication_presets` del proyecto, preseleccionando el primero con
  `mode==="todo"`; si no hay ninguno, botón "Crear preset TODO" que agrega
  `{name:"inicial-todo", mode:"todo", groups:[], target:"gitlab"}` vía
  `upsertPreset` del plan 88 F4 + PUT). Botón "Materializar publicación inicial" ⇒
  reusa EXACTAMENTE la cadena del plan 88 F5: `DevOps.materializePublication` →
  `PipelineYamlPreview` → `CommitPipelineModal` (HITL) → `TriggerPipelineSection`
  (HITL). CERO lógica de publicación nueva.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — extender `DevOps`:
  `environmentPlan: (project) => POST /devops/environments/plan {project}`;
  `environmentApply: (project, paths) => POST /devops/environments/apply {project, paths, confirm: true}`
  (el `confirm:true` lo pone SOLO el handler del botón tras el checkbox — el helper lo
  exige como argumento literal del caller, no lo auto-inyecta en cualquier llamada:
  firma `environmentApply(project: string, paths: string[], confirm: boolean)` y el
  componente pasa el estado del checkbox).
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — `DEVOPS_SECTIONS` +=
  `{ id: "ambientes", label: "Ambientes", render: () => <EnvironmentsSection /> }`.

**Tests PRIMERO** — `Stacky Agents/frontend/src/devops/environmentModel.test.ts`
(vitest TS puro):
- `empty_settings_pacifico_defaults` (IN_/productivas/salida presentes y editables);
- `validate_root_relative_fails`; `validate_segment_traversal_fails`;
- `summarize_counts`; `selectable_only_to_create` (entries mixtos ⇒ solo to_create).
Comando: `npx vitest run src/devops/environmentModel.test.ts`.

**Criterio binario:** vitest verde (5 tests) + `npx tsc --noEmit` 0 errores; el botón
"Crear carpetas" está `disabled` sin checkbox (HITL verificable por código); Paso 2 no
contiene lógica propia de materialización (solo composición de componentes 88).
**Flag:** `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (+ master vía `requires`; + mensaje por
`publications_enabled` para el Paso 2).
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in (activar la flag);
configurar root/layout es USO de la feature con defaults sugeridos.

### F6 — Cierre de la serie: no-regresión + checklist binario

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan89_environments_flag.py tests/test_plan89_environment_layout.py tests/test_plan89_environment_plan_apply.py tests/test_plan89_env_settings_validation.py tests/test_plan89_environments_endpoints.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan88_publications_flag.py tests/test_plan88_publication_spec.py tests/test_plan88_presets_validation.py tests/test_plan88_materialize_endpoint.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_flag.py tests/test_plan87_devops_endpoints.py tests/test_plan87_drafts_validation.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan73_generator_endpoint.py tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest run src/devops/environmentModel.test.ts src/devops/presetsModel.test.ts src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Checklist binario de done:**
- [ ] Flag OFF ⇒ `/api/devops/environments/plan` y `/apply` 404, sección ausente,
      byte-idéntico.
- [ ] Ambiente fresco: plan muestra to_create; apply con confirm crea; los dirs
      existen.
- [ ] Re-inicialización: segundo plan todo `exists_ok`, segundo apply `created == []`,
      0 cambios en disco.
- [ ] Archivo donde va carpeta ⇒ `conflict` reportado e INTACTO tras apply.
- [ ] `"../"` en cualquier input ⇒ nunca se crea nada fuera de root (tests F1/F2/F4).
- [ ] Centinela anti-destrucción verde (el módulo no contiene llamadas de borrado ni
      escritura de archivos).
- [ ] Publicación inicial: 100% composición de 88/73/72 (cero lógica nueva de
      publicación; verificable: `EnvironmentsSection` no importa
      `publication_spec`/renderers, solo componentes del 88).
- [ ] Tests registrados en ambos scripts de ratchet.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Borrado accidental (el riesgo capital) | Ningún API destructivo en el módulo + test centinela F2 sobre el código fuente + apply solo interseca con to_create re-planificado server-side |
| Path traversal vía nombre de proceso o segmento de layout | Sanitización slug (F1) + `_safe_segment` (F1/F3) + `commonpath` (F2) + tests dedicados en F1, F2, F3 y F4 (defensa en 4 capas) |
| Operador apunta root a `C:\` | `validate_root` rechaza raíz de disco (F2/F3) |
| Cliente manda `paths` arbitrarios al apply | El server IGNORA todo path fuera del layout derivado del catálogo real (F4 + test) |
| Carpetas creadas pero publicación inicial falla | Pasos independientes y re-entrantes: re-correr Paso 1 es no-op (idempotente), Paso 2 se reintenta solo |
| Confusión de flags (panel/publicaciones/ambientes) | `requires` al master + banners con el nombre EXACTO de la flag faltante (F5) |
| Plan 87/88 sin implementar | Dependencia y orden declarados; F0-F2 implementables en aislamiento |

## 7. Fuera de scope (v1)

- Crear carpetas en servidores REMOTOS (SSH/UNC/agentes): v1 es filesystem local de
  la máquina del operador (justificación §3.3); remoto exigiría credenciales y otro
  modelo de seguridad.
- Borrar/renombrar/mover carpetas o "desinicializar" ambientes (violaría §3.2).
- Plantillas de contenido inicial DENTRO de las carpetas (archivos seed).
- Múltiples ambientes por proyecto (v1: un `environment_root` por client_profile; N
  ambientes = N proyectos, que es el modelo actual de Stacky).
- Scheduling de la publicación inicial (HITL siempre).

## 8. Glosario

- **Ambiente**: árbol de carpetas de disco que los procesos batch del cliente esperan
  (entrada/productivas/salida) + su primera publicación.
- **Plan-then-apply**: patrón en dos pasos — dry-run que clasifica sin tocar nada, y
  aplicación explícita SOLO de lo aprobado (análogo a `terraform plan/apply`).
- **to_create / exists_ok / conflict / unsafe**: estados del plan de carpetas (§4).
- **environment_root**: raíz absoluta del ambiente en la máquina del operador,
  parametrizada en `devops_environment_settings` del client_profile.
- **folder_layout**: mapeo `kind → subcarpetas relativas`; deriva el árbol del
  process_catalog (el conocimiento vive en el catálogo, no en el código).
- **Publicación inicial (TODO)**: primera publicación del ambiente usando un preset
  `mode="todo"` del plan 88 (resolución dinámica de todo el catálogo).
- **Flujo canónico Pacífico / preset / materializar / HITL / ratchet /
  client_profile**: ver glosarios de los planes 87 §7 y 88 §8.

## 9. Orden de implementación

1. F0 — flag (tests meta verdes).
2. F1 — `build_environment_layout` puro (7 tests).
3. F2 — `plan_environment`/`apply_environment` + centinela anti-destrucción (9 tests).
4. F3 — validación aditiva `devops_environment_settings` (7 tests).
5. F4 — endpoints plan/apply + health key (requiere plan 87 F1).
6. F5 — `environmentModel.ts` + `EnvironmentsSection` + registro en `DEVOPS_SECTIONS`
   (requiere 87 F4/F5 y 88 F3/F4/F5).
7. F6 — cierre de la serie.

## 10. Definición de Hecho (DoD)

- 36 tests backend nombrados (F0:4, F1:7, F2:9, F3:7, F4:9) verdes por archivo con el
  venv; vitest F5 verde; `npx tsc --noEmit` 0 errores.
- No-regresión: suites de planes 87/88/73 + meta-tests del arnés verdes.
- Flag OFF ⇒ byte-idéntico. Checklist F6 completo.
- Idempotencia demostrada por test (re-run ⇒ 0 cambios) y centinela anti-destrucción
  verde: Stacky NO PUEDE borrar nada desde este plan, por construcción.
