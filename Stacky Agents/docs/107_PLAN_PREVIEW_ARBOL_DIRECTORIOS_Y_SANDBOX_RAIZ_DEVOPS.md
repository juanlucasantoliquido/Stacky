# Plan 107 — Preview del ÁRBOL de directorios y RAÍZ SANDBOX de pruebas (panel DevOps)

> **Estado:** PROPUESTO v1 — 2026-07-08
> **Serie:** DevOps (continúa 87-106). Extiende la sección **Ambientes** (Plan 89).
> **Pipeline:** este documento es el paso `proponer`. Sigue `criticar-y-mejorar-plan` → `implementar-plan-stacky` → `supervisar-implementaciones-planes`.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy la sección *Ambientes* del panel DevOps (Plan 89) ya calcula un plan de carpetas a crear (dry-run `POST /api/devops/environments/plan`) y las crea con confirmación (`/apply`), pero lo muestra como una **tabla plana** de rutas relativas y solo puede apuntar a **una** raíz: la guardada en el perfil (`devops_environment_settings.environment_root`). El operador pidió dos mejoras concretas: (1) **VER el árbol de directorios** que se va a crear, renderizado como árbol jerárquico real (no lista plana), antes de crear nada; y (2) poder **redirigir la raíz base a una carpeta sandbox/temporal** para hacer pruebas en el panel sin tocar la ubicación real de producción, con validación dura que impida que la ruta de pruebas pise la real. Ambas cosas son puramente locales (panel DevOps + sistema de archivos vía Flask); no involucran ningún runtime LLM, por lo que la paridad de los 3 runtimes es trivial y total.

**KPI / impacto esperado.**
- **Comprensión:** el operador entiende de un vistazo la estructura completa a crear (profundidad, cuántas carpetas nuevas vs existentes, dónde hay conflictos) sin leer una lista plana de N filas. Meta: 0 clics extra respecto a hoy para ver el árbol (se muestra en el mismo *Paso 2*).
- **Seguridad de pruebas:** el operador puede probar el flujo completo contra una carpeta descartable. Meta medible: **0** rutas de sandbox aceptadas que sean iguales a / contengan / estén contenidas en la raíz de producción (garantizado por test binario `test_sandbox_rejects_overlap_with_production`).
- **Cero regresión:** con ambas flags nuevas en OFF, el comportamiento es **byte-idéntico** al de hoy (garantizado por `test_health_backcompat_without_sandbox_key` y por no enviar `root_override`).

---

## 2. Por qué ahora / gap que cierra

Los últimos planes DevOps leídos (98 bootstrap+PATCH, 99 preview SWR, 100-103 suite/bootstrap/publicar/monitor, 104 doctores IA por sección, 105 consola remota, 106 modelo local) maduraron **generación**, **preflight**, **publicación** y **diagnóstico**, pero la **inicialización de ambientes (Plan 89)** quedó con la UI mínima original: tabla plana + raíz única. Dos fricciones reales que hoy existen en el código:

1. `EnvironmentsSection.tsx:306-327` renderiza `entries` como `<table>` de una columna de `path` + una de `status`. Con layouts profundos o `per_process_subfolder=true` (que multiplica rutas, `environment_init.py:70-73`) la lista se vuelve ilegible y no comunica jerarquía.
2. `api/devops.py:181` toma la raíz **solo** de `profile.devops_environment_settings.environment_root`. Para "probar en otra carpeta" el operador hoy tiene que **editar y guardar** su raíz real (y acordarse de revertirla), con riesgo de crear carpetas de prueba dentro de producción o de dejar la raíz de pruebas guardada como definitiva.

Este plan cierra exactamente esas dos fricciones **reutilizando** el contrato ya existente de Plan 89 (mismos endpoints, mismo `plan_environment`/`apply_environment`, mismos guardarraíles de path traversal `is_safe_segment`/`validate_root`), sin reinventar nada.

---

## 3. Principios y guardarraíles (NO negociables — codificados en las fases)

- **3 runtimes con paridad total.** La feature vive 100% en el panel DevOps (React) + capa FS (Flask, `os.makedirs`). **No hay llamada a ningún runtime LLM** (Codex / Claude Code / GitHub Copilot Pro). Por construcción funciona idéntico en los tres; no hay fallback que definir porque no hay dependencia de runtime. (El botón de doctor IA de la sección, `SectionDoctorButton`, es ortogonal y ya está gateado por su propia flag Plan 104 — no se toca.)
- **Cero trabajo extra al operador.** Ambas capacidades son **opt-in con default OFF**. Con las flags apagadas, la sección se ve y se comporta **igual que hoy**. El árbol reemplaza a la tabla solo cuando su flag está ON; el sandbox aparece solo cuando su flag está ON. Backward-compatible: los endpoints siguen aceptando el body de hoy sin cambios.
- **Human-in-the-loop innegociable.** El `/apply` sigue exigiendo `confirm=True` + `fingerprint` del plan visto (Plan 89). El sandbox agrega un ack explícito adicional (`sandbox_ack=True`). Nada se crea sin confirmación humana. El sandbox NO se autoguarda en el perfil (es estado transitorio de sesión) para que nunca reemplace silenciosamente la raíz real.
- **Mono-operador sin auth.** No se agrega RBAC ni multiusuario. El `current_user` sigue siendo un header sin validar.
- **No degradar seguridad/estabilidad/DX.** Se conservan los guardarraíles de path traversal existentes (`is_safe_segment`, `validate_root`, contención por `realpath`+`commonpath` de `plan_environment`) y se **suma** un guard nuevo que impide solapamiento sandbox↔producción. Ninguna operación borra ni sobrescribe (invariante Plan 89 intacto: `apply_environment` solo `os.makedirs(exist_ok=True)` sobre `to_create`).
- **Toda config/flag desde la UI, default seguro.** Las 2 flags nuevas son `env_only=False` (categoría `devops` de `HarnessFlagsPanel`), default `False`. El operador las prende desde el panel Arnés, no editando `.env`.
- **Sin ambigüedad para modelos menores.** Cada fase indica archivo exacto, símbolo exacto, pseudocódigo, test nombrado, comando de corrida y criterio binario.

---

## 4. Nombres canónicos (usar EXACTAMENTE estos)

| Concepto | Nombre exacto |
|---|---|
| Flag preview de árbol | `STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED` (bool, default `False`) |
| Flag raíz sandbox | `STACKY_DEVOPS_ENV_SANDBOX_ENABLED` (bool, default `False`) |
| Guard puro nuevo (backend) | `validate_sandbox_override(override: str, production_root: str) -> str | None` en `services/environment_init.py` |
| Key de body nueva (plan/apply) | `root_override` (str, opcional) |
| Key de body nueva (apply) | `sandbox_ack` (bool, obligatoria SOLO si `root_override` presente) |
| Health keys nuevas | `env_tree_preview_enabled`, `env_sandbox_enabled` |
| Modelo puro tree (frontend) | `buildDirTree(entries: PlanEntry[]): DirTreeNode[]` en `src/devops/dirTreeModel.ts` |
| Componente tree (frontend) | `DirTreePreview` en `src/components/devops/DirTreePreview.tsx` |

---

## 5. Fases

### F0 — Registrar las 2 flags nuevas (scaffolding, todo desde UI, default OFF)

**Objetivo (1 frase).** Dar de alta `STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED` y `STACKY_DEVOPS_ENV_SANDBOX_ENABLED` como flags editables por UI (categoría DevOps), default OFF, exponiéndolas en `/health` y `/bootstrap`. **Valor:** habilita el opt-in seguro sin tocar comportamiento existente.

**Archivos a editar (rutas exactas):**
1. `Stacky Agents/backend/config.py` — agregar 2 atributos, junto al bloque de `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (config.py:875-877). Patrón EXACTO a copiar:
   ```python
   STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED", "false"
   ).strip().lower() == "true"
   STACKY_DEVOPS_ENV_SANDBOX_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", "false"
   ).strip().lower() == "true"
   ```
   (Default `"false"` — a diferencia de Environments que está en `"true"`. Motivo: son mejoras opt-in.)
2. `Stacky Agents/backend/services/harness_flags.py`:
   - En la tupla `"devops"` (harness_flags.py:177-188) agregar 2 líneas al final del bloque DevOps:
     ```python
     "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED",  # Plan 107 — preview de árbol de ambientes
     "STACKY_DEVOPS_ENV_SANDBOX_ENABLED",  # Plan 107 — raíz sandbox de pruebas
     ```
   - En `FLAG_REGISTRY` agregar 2 `FlagSpec` copiando el shape de Environments (harness_flags.py:1986-2002). Valores EXACTOS:
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED",
         type="bool",
         label="Preview de árbol de ambientes (Plan 107)",
         description=(
             "Plan 107 — En la sección Ambientes, muestra las carpetas a crear como "
             "ÁRBOL jerárquico (en vez de lista plana), con estado por nodo. "
             "SOLO-LECTURA, no cambia qué se crea. Default OFF. Con OFF la sección "
             "usa la tabla plana de siempre."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (depth-1, NO la flag hija Environments)
         default=False,
     ),
     FlagSpec(
         key="STACKY_DEVOPS_ENV_SANDBOX_ENABLED",
         type="bool",
         label="Raíz sandbox de pruebas (Plan 107)",
         description=(
             "Plan 107 — Permite apuntar el plan/apply de Ambientes a una carpeta "
             "sandbox temporal para probar, SIN tocar la raíz de producción. Guard "
             "duro: rechaza rutas que sean iguales/contengan/estén contenidas en la "
             "raíz real. Default OFF. La raíz sandbox NUNCA se guarda en el perfil."
         ),
         group="global",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # master del panel (depth-1)
         default=False,
     ),
     ```
     > **GOTCHA R4 (memoria harness-requires-r4-depth1):** `requires` DEBE apuntar al master `STACKY_DEVOPS_PANEL_ENABLED`, **nunca** a la flag hija `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (crearía cadena profundidad>1 y `validate_requires_graph` la rechaza).
3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — en `_REQUIRES_MAP_FROZEN` (línea 120) agregar, junto a las entradas DevOps (líneas 129-132):
   ```python
   "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 107
   "STACKY_DEVOPS_ENV_SANDBOX_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 107
   ```
   (Si no se agrega, `test_requires_map_is_frozen` falla por drift — es el objetivo del centinela.)
4. `Stacky Agents/backend/services/harness_flags_help.py` — agregar 2 entradas `PlainHelp` copiando el shape de `STACKY_DEVOPS_ENVIRONMENTS_ENABLED` (harness_flags_help.py:614-618). Texto llano (Plan 86):
   ```python
   "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED": PlainHelp(
       what="Muestra las carpetas del ambiente como un árbol desplegable en vez de una lista.",
       on_effect="Si la activás: en 'Ambientes' ves un árbol con las carpetas nuevas resaltadas; no cambia qué se crea.",
       off_effect="Si la apagás: ves la lista plana de siempre.",
       example="Como ver el explorador de archivos con carpetas anidadas, en vez de un renglón por ruta.",
   ),
   "STACKY_DEVOPS_ENV_SANDBOX_ENABLED": PlainHelp(
       what="Deja probar la creación de carpetas en una ubicación descartable sin tocar la carpeta real.",
       on_effect="Si la activás: aparece un modo 'sandbox' donde elegís una carpeta de prueba; Stacky rechaza cualquier ruta que se pise con la de producción.",
       off_effect="Si la apagás: el ambiente usa siempre la raíz real guardada en el perfil.",
       example="Como maquetar el mueble en el garaje antes de armarlo en el living.",
   ),
   ```
5. `Stacky Agents/backend/api/devops.py` — en `_health_payload()` (devops.py:36-57) agregar 2 keys antes del `return` de cierre:
   ```python
   "env_tree_preview_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED", False)),  # Plan 107
   "env_sandbox_enabled": bool(getattr(cfg, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", False)),  # Plan 107
   ```
   (`/bootstrap` las hereda automáticamente porque reusa `_health_payload()` — devops.py:74.)

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan107_flags.py`. Casos:
- `test_flags_registered_in_devops_category` — ambas keys están en la tupla `devops` de `harness_flags.py` (importar el mapa de categorías y assert `in`).
- `test_flags_default_off` — `config.config.STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED is False` y `..._SANDBOX_ENABLED is False` sin env vars.
- `test_flags_require_panel_master` — en `FLAG_REGISTRY`, ambos `FlagSpec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_health_exposes_new_keys` — `_health_payload()` contiene `env_tree_preview_enabled` y `env_sandbox_enabled` (bool).
- `test_health_backcompat_without_sandbox_key` — con ambas flags OFF, todas las demás keys de `_health_payload()` conservan su valor esperado (no se rompió ninguna existente).

Registrar el archivo en `Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1` (agregar `test_plan107_flags.py` a la lista `HARNESS_TEST_FILES`). **Obligatorio** (memoria ratchet: todo test backend nuevo va en ambos scripts o el meta-test del Plan 49 falla). Repetir este registro en F1 y F2 con sus archivos.

**Comando de tests (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan107_flags.py tests/test_harness_flags_requires.py -q
```

**Criterio de aceptación BINARIO:** los dos archivos anteriores pasan en verde (0 fallos). `venv/Scripts/python.exe -c "import config; print(config.config.STACKY_DEVOPS_ENV_SANDBOX_ENABLED)"` imprime `False`.

**Flag que la protege / default:** las flags mismas; default `False`. **Impacto por runtime:** ninguno (capa config). **Fallback:** N/A. **Trabajo del operador:** ninguno (opt-in default off).

---

### F1 — Guard puro `validate_sandbox_override` (backend, sin I/O)

**Objetivo (1 frase).** Función pura que decide si una raíz sandbox propuesta es aceptable frente a la raíz de producción, impidiendo cualquier solapamiento. **Valor:** núcleo de seguridad del sandbox, testeable aislado.

**Archivo a editar:** `Stacky Agents/backend/services/environment_init.py` — agregar función nueva (después de `validate_root`, línea 107).

**Pseudocódigo EXACTO:**
```python
def validate_sandbox_override(override: str, production_root: str) -> str | None:
    """None si el override es un sandbox seguro; string de error si no.
    PURO salvo os.path.realpath (resuelve symlinks del tramo existente, igual
    criterio que plan_environment). NUNCA lanza.

    Reglas, en orden:
      1) validate_root(override) debe pasar (absoluta, no raíz de disco).
      2) Si production_root es válido (validate_root(production_root) is None),
         override NO puede solaparse con producción:
           a = realpath(abspath(override)); b = realpath(abspath(production_root))
           - a == b                      -> 'sandbox_igual_a_produccion'
           - commonpath([a, b]) == b     -> 'sandbox_dentro_de_produccion'
           - commonpath([a, b]) == a     -> 'produccion_dentro_de_sandbox'
           - ValueError (drives distintos) -> OK (no hay solapamiento posible)
      Si production_root NO es válido/está vacío, se omite el chequeo de
      solapamiento (no hay producción real que proteger) y se acepta si (1) pasó.
    """
    err = validate_root(override)
    if err:
        return err
    if validate_root(production_root or "") is not None:
        return None  # sin producción válida no hay nada que pisar
    a = os.path.realpath(os.path.abspath(override))
    b = os.path.realpath(os.path.abspath(production_root))
    if a == b:
        return "sandbox_igual_a_produccion"
    try:
        common = os.path.commonpath([a, b])
    except ValueError:
        return None  # drives distintos: imposible solapar
    if common == b:
        return "sandbox_dentro_de_produccion"
    if common == a:
        return "produccion_dentro_de_sandbox"
    return None
```

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan107_sandbox_guard.py`. Casos (usar rutas absolutas construidas con `tmp_path`; en Windows `os.sep` es `\\`):
- `test_override_invalid_root_rejected` — override relativo o raíz de disco → mensaje de `validate_root`.
- `test_override_equal_to_production_rejected` — override == production → `'sandbox_igual_a_produccion'`.
- `test_override_inside_production_rejected` — override = `production/sub` → `'sandbox_dentro_de_produccion'`.
- `test_production_inside_override_rejected` — override = ancestro de production → `'produccion_dentro_de_sandbox'`.
- `test_disjoint_sibling_ok` — override y production hermanos distintos → `None`.
- `test_different_drive_ok` (skip si no Windows) — override en `D:\...`, production en `C:\...` → `None`.
- `test_no_production_configured_accepts_valid_override` — `production_root=""` y override válido → `None`.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan107_sandbox_guard.py -q
```

**Criterio BINARIO:** los 7 casos pasan. `import services.environment_init as e; e.validate_sandbox_override` es callable.

**Flag/default:** protegida aguas arriba por `STACKY_DEVOPS_ENV_SANDBOX_ENABLED` (la función pura no lee flags). **Impacto runtime:** ninguno. **Trabajo del operador:** ninguno.

---

### F2 — Wiring API: `root_override` + `sandbox_ack` en plan/apply

**Objetivo (1 frase).** Permitir que `/environments/plan` y `/environments/apply` operen sobre la raíz sandbox cuando la flag está ON, validando siempre server-side y sin romper el contrato actual. **Valor:** hace usable el sandbox de punta a punta con HITL.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py`.

**Cambio 1 — `_load_env_context(body)` (devops.py:173-188):** agregar resolución de override.
```python
def _load_env_context(body):
    project = body.get("project")
    if not project:
        return None, (jsonify({"error": "project es obligatorio"}), 400)
    profile = load_client_profile(project) or {}
    settings = profile.get("devops_environment_settings")
    settings = settings if isinstance(settings, dict) else {}
    production_root = settings.get("environment_root") or ""

    # Plan 107 — resolución de raíz efectiva (sandbox opt-in, server-side).
    root = production_root
    sandbox_active = False
    override = body.get("root_override")
    if override is not None and str(override).strip():
        if not getattr(_config.config, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", False):
            return None, (jsonify({"error": "el modo sandbox está deshabilitado",
                                   "kind": "sandbox_disabled"}), 400)
        from services.environment_init import validate_sandbox_override
        serr = validate_sandbox_override(str(override), production_root)
        if serr:
            return None, (jsonify({"error": f"raíz sandbox inválida: {serr}",
                                   "kind": "sandbox_invalid", "reason": serr}), 400)
        root = str(override)
        sandbox_active = True

    err = validate_root(root or "")
    if err:
        return None, (jsonify({"error": f"environment_root invalido o no configurado: {err}",
                               "kind": "environment_root_invalid"}), 400)
    catalog = profile.get("process_catalog")
    rel_paths = build_environment_layout(catalog if isinstance(catalog, list) else [], settings)
    return (root, rel_paths, sandbox_active), None
```
> **Nota:** el layout (`rel_paths`) se deriva del MISMO catálogo/settings; solo cambia la base `root`. Así el árbol de prueba es estructuralmente idéntico al de producción.

**Cambio 2 — `environment_plan_route` (devops.py:191-199):** desempaquetar la tupla de 3 y devolver `sandbox_active` en la respuesta (aditivo).
```python
ctx, err = _load_env_context(request.get_json(silent=True) or {})
if err: return err
root, rel_paths, sandbox_active = ctx
result = plan_environment(root, rel_paths)
result["sandbox_active"] = sandbox_active  # Plan 107 — la UI muestra el badge
return jsonify(result)
```

**Cambio 3 — `environment_apply_route` (devops.py:202-226):** exigir `sandbox_ack` cuando hay override; re-desempaquetar la tupla.
```python
body = request.get_json(silent=True) or {}
if body.get("confirm") is not True:
    return jsonify({"error": "confirm=True requerido (HITL)"}), 400
# Plan 107 — ack extra cuando se opera en sandbox.
if body.get("root_override") is not None and str(body.get("root_override")).strip():
    if body.get("sandbox_ack") is not True:
        return jsonify({"error": "sandbox_ack=True requerido para crear en la raíz sandbox",
                        "kind": "sandbox_ack_required"}), 400
fingerprint = body.get("fingerprint")
if not isinstance(fingerprint, str) or not fingerprint:
    return jsonify({"error": "fingerprint del plan es obligatorio (respuesta de /plan)"}), 400
ctx, err = _load_env_context(body)
if err: return err
root, rel_paths, sandbox_active = ctx
if fingerprint != layout_fingerprint(root, rel_paths):
    return jsonify({"error": "el layout cambio desde el ultimo plan; recalcular el plan",
                    "kind": "plan_stale"}), 409
# ... resto idéntico a hoy (requested/approved/apply_environment) ...
result = apply_environment(root, approved)
result["ignored_not_in_layout"] = sorted(set(requested) - set(rel_paths))
result["sandbox_active"] = sandbox_active  # Plan 107
return jsonify(result)
```
> **Invariante clave:** `layout_fingerprint` ya incluye `abspath(root)` (environment_init.py:88-92). Como `root` es el sandbox en ambos lados (plan y apply), el handshake anti-stale funciona sin cambios. Nunca se confía en la lista del cliente: `apply_environment` re-planifica server-side (environment_init.py:170).

**Tests PRIMERO — archivo:** `Stacky Agents/backend/tests/test_plan107_sandbox_endpoints.py` (usar el `app` de test como en `test_plan89_environments_endpoints.py`; monkeypatch de `load_client_profile` para inyectar `environment_root` de producción y catálogo). Casos:
- `test_plan_without_override_is_bytewise_like_today` — sin `root_override`, la respuesta de `/plan` NO cambia respecto a Plan 89 salvo la key aditiva `sandbox_active=False`.
- `test_plan_override_rejected_when_flag_off` — flag OFF + `root_override` presente → 400 `kind=sandbox_disabled`.
- `test_plan_override_overlapping_rejected` — flag ON + override dentro de producción → 400 `kind=sandbox_invalid`, `reason=sandbox_dentro_de_produccion`.
- `test_plan_override_valid_uses_sandbox_root` — flag ON + override disjunto válido → 200, `root` de la respuesta == override, `sandbox_active=True`.
- `test_apply_override_requires_ack` — flag ON + override válido + `confirm=True` pero sin `sandbox_ack` → 400 `kind=sandbox_ack_required`.
- `test_apply_override_creates_in_sandbox_only` — con `sandbox_ack=True` y `tmp_path` como sandbox, se crean carpetas bajo el sandbox y **ninguna** bajo producción (assert `not os.path.isdir(prod/...)`).
- `test_apply_fingerprint_stale_on_sandbox` — fingerprint de otra raíz → 409 `kind=plan_stale`.

Registrar el archivo en ambos `run_harness_tests.*`.

**Comando (desde `Stacky Agents/backend`):**
```
venv/Scripts/python.exe -m pytest tests/test_plan107_sandbox_endpoints.py tests/test_plan89_environments_endpoints.py -q
```
(Incluye el suite del 89 como **no-regresión**: debe seguir 100% verde.)

**Criterio BINARIO:** ambos archivos verdes. El del 89 sin fallos nuevos.

**Flag/default:** `STACKY_DEVOPS_ENV_SANDBOX_ENABLED`, default OFF (override rechazado con flag off). **Impacto runtime:** ninguno (endpoints FS). **Fallback:** con flag off, endpoints se comportan igual que Plan 89. **Trabajo del operador:** ninguno.

---

### F3 — Modelo puro `buildDirTree` (frontend, sin React)

**Objetivo (1 frase).** Función pura que convierte la lista plana `PlanEntry[]` en un árbol jerárquico con estado y conteos por nodo. **Valor:** núcleo testeable del preview de árbol.

**Archivo a crear:** `Stacky Agents/frontend/src/devops/dirTreeModel.ts`.

**Contrato EXACTO:**
```ts
import type { PlanEntry, PlanEntryStatus } from './environmentModel';

export type NodeStatus = PlanEntryStatus | 'mixed';

export interface DirTreeNode {
  name: string;                 // último segmento ("b" para "a/b")
  path: string;                 // ruta relativa completa ("a/b"), separador '/'
  children: DirTreeNode[];      // ordenados asc por name (localeCompare)
  selfStatus: PlanEntryStatus | null; // status del entry EXACTO en este path, o null si es intermedio
  status: NodeStatus;           // rollup del subárbol (ver reglas)
  counts: Record<PlanEntryStatus, number>; // conteo de entries reales en el subárbol
}

/**
 * buildDirTree — nesting determinístico de entries por '/'.
 * Reglas de rollup de `status` (prioridad de peligro):
 *   - si algún entry del subárbol es 'conflict' o 'unsafe' -> 'mixed' (peligro, se pinta danger)
 *   - si no, y algún entry es 'to_create' y algún otro 'exists_ok' -> 'mixed'
 *   - si todos los entries del subárbol son 'to_create' -> 'to_create'
 *   - si todos son 'exists_ok' -> 'exists_ok'
 * `counts` suma SOLO entries reales (los intermedios sin entry propio no cuentan).
 * Entradas duplicadas por path: la última gana en selfStatus (determinístico).
 * Paths con separador '\\' se normalizan a '/' antes de dividir.
 */
export function buildDirTree(entries: PlanEntry[]): DirTreeNode[] { /* ... */ }

/** Suma de counts de una lista de nodos raíz (para el encabezado del árbol). */
export function rollupCounts(nodes: DirTreeNode[]): Record<PlanEntryStatus, number> { /* ... */ }
```

**Algoritmo (determinístico):** mantener un `Map<string, DirTreeNode>` por path; para cada `entry`, normalizar `path` (`replace(/\\/g,'/')`), `split('/')`, ir creando nodos intermedios (selfStatus=null) y setear `selfStatus=entry.status` en el terminal. Tras insertar todo, recorrer bottom-up para computar `counts` y `status` según las reglas. Ordenar `children` por `name.localeCompare`. Devolver los nodos de primer nivel ordenados.

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/devops/dirTreeModel.test.ts` (vitest). Casos:
- `nests two-level paths` — `["a", "a/b"]` → un root `a` con hijo `b`.
- `intermediate node without own entry` — `["x/y"]` (sin `"x"`) → root `x` con `selfStatus=null` y `status` derivado de `y`.
- `rollup danger dominates` — subárbol con un `conflict` → nodo padre `status='mixed'`.
- `rollup all to_create` — todos `to_create` → padre `status='to_create'`.
- `counts only real entries` — cuenta correcta ignorando intermedios.
- `backslash paths normalized` — `"a\\b"` se trata igual que `"a/b"`.
- `deterministic order` — children ordenados alfabéticamente.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/devops/dirTreeModel.test.ts
```

**Criterio BINARIO:** los 7 casos verdes.

**Flag/default:** consumido solo cuando `env_tree_preview_enabled` (la función pura no lee flags). **Impacto runtime:** ninguno (browser). **Trabajo del operador:** ninguno.

---

### F4 — Componente `DirTreePreview` + montaje en la sección (reemplaza la tabla plana bajo flag)

**Objetivo (1 frase).** Render jerárquico, lindo y desplegable del árbol de carpetas, con estado por nodo, leyenda y contadores, montado en el Paso 2 solo cuando la flag de preview está ON. **Valor:** la mejora visible #1 del operador.

**Archivo a crear:** `Stacky Agents/frontend/src/components/devops/DirTreePreview.tsx`.

**Props e interacción:**
```ts
export interface DirTreePreviewProps {
  entries: PlanEntry[];             // del /plan
  sandboxActive?: boolean;          // muestra badge "SANDBOX (pruebas)"
  rootLabel: string;                // la raíz efectiva a mostrar como nodo raíz
}
```
**Requisitos de UX (criterios de aceptación de esta fase — el operador pidió UI linda/profesional/innovadora):**
1. **Árbol anidado** con indentación por nivel y conector visual; carpetas colapsables (estado `expanded` por nodo, default expandido hasta 2 niveles, resto colapsado). Reusar el lenguaje visual de `BlockTree.tsx` y las clases de `devops.module.css` (no inventar CSS nuevo salvo lo mínimo; si hace falta, agregar clases al final de `devops.module.css`, theme-aware light/dark).
2. **Estado por nodo** con chip de color: `to_create` = verde/acento "nuevo" (usar `styles.textSuccess`), `exists_ok` = atenuado (`styles.textMuted`), `mixed`/`conflict`/`unsafe` = peligro (`styles.textDanger`) con tooltip del `reason`. Los nodos `to_create` llevan un badge "nuevo".
3. **Encabezado con contadores** (`rollupCounts`): "N nuevas · M existentes · K conflictos" — misma info que el `summary` de hoy pero sobre el árbol.
4. **Chips de filtro** (innovador, opt-in visual, sin cambiar datos): "Todo | Solo nuevas | Solo conflictos" que ocultan nodos sin coincidencia en el subárbol (puro cliente, sin refetch).
5. **Badge SANDBOX** prominente cuando `sandboxActive` (color distinto, texto "PRUEBAS — no es producción").
6. **Botón "Copiar árbol"** que copia una representación de texto indentada (útil para pegar en un ticket). Degradación: si `navigator.clipboard` no existe, el botón queda oculto.
7. **Accesibilidad:** cada toggle es un `<button>` con `aria-expanded`; no usar `window.confirm`/`alert` (memoria Plan 105 UX-C4).

**Montaje — editar `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx`** (bloque Paso 2, hoy tabla en líneas 306-330):
```tsx
{entries.length > 0 && (
  <>
    {ctx.health.env_tree_preview_enabled === true ? (
      <DirTreePreview
        entries={entries}
        sandboxActive={sandboxActive}
        rootLabel={effectiveRoot}
      />
    ) : (
      /* tabla plana EXACTAMENTE como hoy (líneas 308-327) — fallback */
    )}
    {/* summary + checkbox confirm + botón Crear: SIN cambios */}
  </>
)}
```
(Guardar el estado `sandboxActive` y `effectiveRoot` que llega de F5; si F5 aún no está, `sandboxActive=false` y `effectiveRoot=settings.environment_root`.)

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/components/devops/DirTreePreview.test.tsx` (vitest + @testing-library/react, patrón de los `.test.tsx` existentes del panel). Casos:
- `renders nested folders from flat entries`.
- `shows "nuevo" badge on to_create nodes`.
- `collapse hides children` (click en toggle oculta subárbol).
- `filter "solo nuevas" hides exists_ok-only subtrees`.
- `shows SANDBOX badge when sandboxActive`.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/components/devops/DirTreePreview.test.tsx
npx tsc --noEmit
```

**Criterio BINARIO:** vitest verde + `tsc --noEmit` 0 errores. Agregar `env_tree_preview_enabled?: boolean; env_sandbox_enabled?: boolean;` al tipo de retorno de `DevOps.health` en `endpoints.ts` (líneas 3077-3091) para que `tsc` acepte `ctx.health.env_tree_preview_enabled`.

**Flag/default:** `STACKY_DEVOPS_ENV_TREE_PREVIEW_ENABLED` OFF → se renderiza la tabla plana de siempre. **Impacto runtime:** ninguno. **Fallback:** tabla plana (comportamiento Plan 89). **Trabajo del operador:** ninguno.

---

### F5 — UI del modo sandbox en la sección (toggle + raíz de pruebas + pass-through)

**Objetivo (1 frase).** Exponer en el Paso 2 un modo sandbox opt-in donde el operador ingresa una raíz de prueba transitoria, ve la raíz de producción read-only para contraste, y el plan/apply usan la raíz sandbox con el ack extra. **Valor:** la mejora #2 del operador, segura por diseño.

**Archivos a editar:**
1. `Stacky Agents/frontend/src/api/endpoints.ts` — extender firmas (aditivo, backward-compatible):
   ```ts
   environmentPlan: (project: string, rootOverride?: string) =>
     api.post<EnvironmentPlanResponse & { sandbox_active?: boolean }>(
       "/api/devops/environments/plan",
       rootOverride ? { project, root_override: rootOverride } : { project }),
   environmentApply: (project: string, paths: string[], confirm: boolean,
                      fingerprint: string, rootOverride?: string, sandboxAck?: boolean) =>
     api.post<EnvironmentApplyResponse & { sandbox_active?: boolean }>(
       "/api/devops/environments/apply",
       rootOverride
         ? { project, paths, confirm, fingerprint, root_override: rootOverride, sandbox_ack: sandboxAck === true }
         : { project, paths, confirm, fingerprint }),
   ```
   (Cuando `rootOverride` es `undefined`, el body es EXACTAMENTE el de hoy — cero regresión.)
2. `Stacky Agents/frontend/src/devops/environmentModel.ts` — agregar `sandbox_active?: boolean` a `EnvironmentPlanResponse` y `EnvironmentApplyResponse`; agregar helper puro:
   ```ts
   /** validateSandboxOverrideLocal — espejo del guard backend para feedback inmediato.
    * Devuelve mensaje de error o null. NO es fuente de verdad (backend re-valida). */
   export function validateSandboxOverrideLocal(override: string, productionRoot: string): string | null { /* misma lógica de solapamiento por prefijo de string normalizado + validateRootLocal */ }
   ```
3. `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx` — agregar estado y UI del sandbox (solo si `ctx.health.env_sandbox_enabled === true`):
   - Estado nuevo: `const [sandboxMode, setSandboxMode] = useState(false); const [sandboxRoot, setSandboxRoot] = useState(''); const [sandboxActive, setSandboxActive] = useState(false);`
   - `effectiveRoot = sandboxMode && sandboxRoot ? sandboxRoot : settings.environment_root`.
   - En `handleCalculatePlan`: pasar `sandboxMode && sandboxRoot ? sandboxRoot : undefined` como 2º arg de `DevOps.environmentPlan`; setear `setSandboxActive(resp.sandbox_active === true)`.
   - En `handleCreateFolders`: pasar `rootOverride` y `sandboxAck = sandboxMode` a `DevOps.environmentApply`; el re-plan post-apply también con override.
   - UI (dentro del Paso 2, arriba del botón "Calcular plan"), envuelta en `{ctx.health.env_sandbox_enabled === true && (...)}`:
     - Toggle "Modo sandbox (pruebas)" (`<input type=checkbox>`).
     - Cuando ON: input de `sandboxRoot` (placeholder `C:\temp\stacky-sandbox`), y una línea read-only "Producción: {settings.environment_root}" para contraste.
     - Feedback inmediato: si `validateSandboxOverrideLocal(sandboxRoot, settings.environment_root)` devuelve error, mostrarlo en `styles.textDanger` y **deshabilitar** "Calcular plan".
     - Badge visible "SANDBOX — no es producción" (reusar el badge de `DirTreePreview` o `styles`).
   - El `sandboxRoot` **NO** se guarda en el perfil (no llamar `saveSettings` con él). Es estado de sesión.

**Tests PRIMERO — archivo:** `Stacky Agents/frontend/src/devops/environmentModel.sandbox.test.ts` (vitest, sobre el helper puro; testear el componente completo es opcional pero el helper es obligatorio). Casos:
- `local guard rejects equal path`.
- `local guard rejects override inside production`.
- `local guard rejects production inside override`.
- `local guard accepts disjoint`.
- `local guard rejects non-absolute override`.

**Comando (desde `Stacky Agents/frontend`):**
```
npx vitest run src/devops/environmentModel.sandbox.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** vitest verde + `tsc --noEmit` 0 errores. Manual smoke (opcional, no bloquea CI): con ambas flags ON, ingresar una sandbox disjunta → "Calcular plan" muestra árbol con badge SANDBOX; ingresar una subcarpeta de producción → error inline y botón deshabilitado.

**Flag/default:** `STACKY_DEVOPS_ENV_SANDBOX_ENABLED` OFF → toda la UI de sandbox está ausente; `environmentPlan`/`Apply` se llaman sin override (idéntico a hoy). **Impacto runtime:** ninguno. **Fallback:** flujo Plan 89 sin sandbox. **Trabajo del operador:** ninguno (opt-in).

---

### F6 — Cierre: defaults, no-regresión global y DoD

**Objetivo (1 frase).** Sellar el plan: defaults del arnés, suites no-regresión y checklist final.

**Acciones:**
1. `Stacky Agents/backend/harness_defaults.env` — **NO** agregar líneas nuevas manualmente. El generador real es `deployment/export_harness_defaults.py` (memoria drift 87-91): ambas flags default OFF no cambian el `.env` de deploy. Verificar que los tests centinela de `harness_defaults` siguen coherentes tras F0.
2. Confirmar registro de los 3 archivos de test backend nuevos (`test_plan107_flags.py`, `test_plan107_sandbox_guard.py`, `test_plan107_sandbox_endpoints.py`) en `run_harness_tests.sh` **y** `.ps1`.
3. Correr no-regresión dirigida (desde `Stacky Agents/backend`):
   ```
   venv/Scripts/python.exe -m pytest tests/test_plan107_flags.py tests/test_plan107_sandbox_guard.py tests/test_plan107_sandbox_endpoints.py tests/test_plan89_environments_endpoints.py tests/test_plan89_environments_flag.py tests/test_harness_flags_requires.py tests/test_harness_flags.py -q
   ```
4. Frontend (desde `Stacky Agents/frontend`):
   ```
   npx vitest run src/devops/dirTreeModel.test.ts src/components/devops/DirTreePreview.test.tsx src/devops/environmentModel.sandbox.test.ts
   npx tsc --noEmit
   ```

**Criterio BINARIO global (DoD):**
- [ ] Todos los comandos de F0-F5 y F6 en verde; `tsc --noEmit` 0 errores.
- [ ] Con **ambas flags OFF**: sección Ambientes idéntica a Plan 89 (tabla plana, sin sandbox); `/plan` y `/apply` aceptan el body de hoy sin cambios (probado por `test_plan_without_override_is_bytewise_like_today`).
- [ ] Ningún test del Plan 89 regresiona.
- [ ] `validate_sandbox_override` rechaza todo solapamiento (7/7 casos F1).
- [ ] Los 3 archivos de test backend registrados en ambos scripts del arnés.

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El operador crea carpetas de prueba dentro de producción. | Guard `validate_sandbox_override` (F1) + espejo local (F5): rechaza igualdad/contención en ambas direcciones. Server-side es la fuente de verdad. |
| El sandbox root se guarda por error como raíz real. | El `sandboxRoot` es estado de sesión, NUNCA se persiste en el perfil (F5). |
| Se aplica un plan viejo tras cambiar de raíz. | `layout_fingerprint` incluye `abspath(root)` → cambiar de raíz invalida el fingerprint → 409 `plan_stale` (F2). |
| Cliente malicioso/viejo manda `root_override` con flag off. | 400 `kind=sandbox_disabled` (F2). |
| El árbol rompe con paths raros (backslash, duplicados). | `buildDirTree` normaliza `\\`→`/` y es determinístico ante duplicados (F3, tests). |
| Drift del mapa `requires`. | Centinela `test_requires_map_is_frozen` + alta explícita en `_REQUIRES_MAP_FROZEN` (F0). |
| Cadena `requires` profundidad>1 (gotcha R4). | Ambas flags requieren el master `STACKY_DEVOPS_PANEL_ENABLED`, no la flag hija (F0). |

---

## 7. Fuera de scope

- Editar/mover/borrar carpetas existentes (Plan 89 nunca borra; se mantiene).
- Persistir múltiples raíces sandbox o un historial de pruebas.
- Copiar/sincronizar archivos entre sandbox y producción.
- Cambiar el contrato de `plan_environment`/`apply_environment` más allá de la key aditiva `sandbox_active`.
- Cualquier interacción con runtimes LLM (Codex/Claude/Copilot) — la feature no los usa.
- Drag-and-drop o edición del árbol (solo preview de lectura).

---

## 8. Glosario (términos Stacky para modelos menores)

- **Panel DevOps:** pestaña del frontend (`frontend/src/components/devops/`) para crear pipelines, publicar procesos e inicializar ambientes. Gateada por `STACKY_DEVOPS_PANEL_ENABLED` (flag master).
- **Sección Ambientes (Plan 89):** wizard que deriva un árbol de carpetas del `process_catalog` del cliente y las crea con confirmación. Endpoints `/api/devops/environments/plan` (dry-run) y `/apply` (crea).
- **`environment_root`:** raíz base absoluta donde se crean las carpetas, guardada en `client_profile.devops_environment_settings.environment_root`.
- **`client_profile`:** JSON de configuración por proyecto (`services/client_profile.py`), leído con `load_client_profile(project)`.
- **`plan-then-apply` / HITL:** primero se muestra qué se hará (plan), y solo con `confirm=True` + `fingerprint` se ejecuta. Human-in-the-loop: nada se crea sin confirmación humana.
- **`layout_fingerprint`:** sha256 de `abspath(root)` + rutas; detecta si el plan cambió entre el dry-run y el apply.
- **FlagSpec / FLAG_REGISTRY:** registro declarativo de flags del arnés (`services/harness_flags.py`); `env_only=False` = editable desde `HarnessFlagsPanel` (UI).
- **PlainHelp:** ayuda en lenguaje llano por flag (`services/harness_flags_help.py`, Plan 86).
- **`_REQUIRES_MAP_FROZEN`:** mapa congelado flag→dependencia; un centinela lo compara contra `FLAG_REGISTRY` para evitar drift.
- **`is_safe_segment` / `validate_root`:** guardarraíles de path traversal ya existentes en `environment_init.py`.
- **venv del repo:** `Stacky Agents/backend/venv` (Python 3.13). Correr pytest **por archivo**.

---

## 9. Orden de implementación (secuencial)

1. **F0** — flags (config + registry + requires frozen + help + health) y su test.
2. **F1** — `validate_sandbox_override` puro y su test.
3. **F2** — wiring API plan/apply (`root_override` + `sandbox_ack`) y su test + no-regresión 89.
4. **F3** — `buildDirTree` puro (vitest).
5. **F4** — `DirTreePreview` + montaje bajo flag + tipo health en endpoints (vitest + tsc).
6. **F5** — UI sandbox + firmas endpoints + helper local (vitest + tsc).
7. **F6** — cierre, no-regresión global, DoD.

---

## 10. Definición de Hecho (DoD) — resumen binario

Hecho cuando: (a) las 4 suites backend nuevas/relevantes y las 3 vitest nuevas están verdes; (b) `tsc --noEmit` sin errores; (c) con ambas flags OFF el sistema es byte-idéntico a hoy; (d) el guard de solapamiento sandbox↔producción rechaza los 4 casos de contención; (e) los 3 tests backend nuevos están registrados en ambos scripts del arnés; (f) `_REQUIRES_MAP_FROZEN` incluye las 2 flags nuevas apuntando al master del panel.
