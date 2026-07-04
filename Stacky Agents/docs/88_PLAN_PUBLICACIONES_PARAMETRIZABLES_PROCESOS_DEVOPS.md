# Plan 88 — Publicaciones parametrizables de procesos batch/agenda/TODO desde el panel DevOps

**Estado:** PROPUESTO
**Fecha:** 2026-07-03
**Serie DevOps:** plan 2 de 3.
**Dependencias:** plan 87 (`87_PLAN_PANEL_DEVOPS_CREADOR_GRAFICO_PIPELINES.md`, commit
`59918622` — panel DevOps base). Este plan agrega la sección **Publicaciones** a
`DEVOPS_SECTIONS` (punto de extensión definido en plan 87 F4). El plan 3 de la serie
(inicialización de ambientes) dependerá de ÉSTE (reusa el materializador de
publicaciones). Además requiere implementados los planes 45/71/72/73 — VERIFICADO:

| Pieza existente | Evidencia (archivo:línea) |
|---|---|
| process_catalog editable por UI + allowlist kinds | `backend/api/client_profile.py:57` (`ALLOWED_PROCESS_KINDS = {"entry","processing","output"}`), `:138-156` |
| GET/PUT client_profile | `backend/api/client_profile.py:94,127` |
| Loader del catálogo | `backend/api/agents.py:1436` (`_load_process_catalog`) |
| PipelineSpec + dict_to_spec + validate | `backend/services/pipeline_spec.py:55,69,112` |
| Renderers YAML | `backend/services/pipeline_renderers.py:23,126` |
| POST /api/pipeline-generator/preview y /commit (HITL) | `backend/api/pipeline_generator.py:34,52,59-60` |
| Trigger/monitor CI HITL | `backend/api/ci.py:26,76,139,174` |
| Panel DevOps: `DEVOPS_SECTIONS`, `api/devops.py`, flag master | plan 87 F1/F4 (`frontend/src/pages/DevOpsPage.tsx`, `backend/api/devops.py`) |

> **Nota de secuencia:** si al implementar este plan el 87 aún no está implementado,
> implementarlo primero. Este doc NO redefine nada del 87; solo lo extiende.

---

## 1. Objetivo + KPI

Que el operador genere **publicaciones** (deploy/publicación) de procesos del catálogo
del cliente de forma parametrizable: **una selección** de procesos batch, **los de
agenda**, o **TODO** junto — donde "TODO" se resuelve DINÁMICAMENTE contra el
process_catalog al momento de materializar (si el catálogo creció, TODO los incluye
sin editar nada). La publicación se materializa como **pipeline**: una función PURA
convierte `preset + process_catalog` en un dict `PipelineSpec`, y de ahí TODO reusa el
plan 73 (preview/commit YAML) y el plan 72 (trigger/monitor). **Prohibido generar YAML
a mano en cualquier punto de este plan.**

**KPI / impacto esperado:**
- Materializar y previewear la publicación "TODO" del catálogo Pacífico (flujo
  Mul2Bane→IncHost→RSCore→RsExtrae) en < 1 minuto y 0 líneas de YAML a mano.
- Presets reutilizables: definir 1 vez "publicación quincenal batch", ejecutarla N veces.
- Catálogo crece ⇒ la publicación TODO crece sola (resolución dinámica, criterio binario F1).

## 2. Por qué ahora / gap que cierra

El plan 87 deja el panel DevOps con un creador gráfico de pipelines GENÉRICO: el
operador arma stages/jobs/steps a mano. Pero el 80% del trabajo DevOps real del
dominio es repetitivo y ya está catalogado: publicar procesos que YA están en el
process_catalog (plan 45). Hoy ese conocimiento (qué procesos existen, de qué tipo
son, en qué orden se cargan) no se aprovecha para generar pipelines. Este plan cierra
ese gap: del catálogo al pipeline en un click parametrizable, sin duplicar ni una
pieza del motor 71/72/73.

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop:** materializar es SOLO-LECTURA (produce un spec, cero efectos).
   Commit al repo exige el modal HITL del plan 87 (checkbox ⇒ `confirm:true`,
   `api/pipeline_generator.py:59-60`). Trigger reusa el HITL del plan 72. Nada corre solo.
2. **Mono-operador, sin auth real.**
3. **Flag propia** `STACKY_DEVOPS_PUBLICATIONS_ENABLED`: en `FLAG_REGISTRY`
   (`services/harness_flags.py`) con `requires="STACKY_DEVOPS_PANEL_ENABLED"`
   (mecanismo del plan 82, `harness_flags.py:30`), categoría `devops` (creada por plan
   87 F0), `env_only=False` ⇒ **alta obligatoria en `config.py`** (gotcha plan 81),
   **SIN `default=` explícito** (gotcha `_CURATED_DEFAULTS_ON`), **con entrada
   `PlainHelp`** en `services/harness_flags_help.py` (meta-test plan 86).
4. **Byte-idéntico con flag OFF:** endpoints nuevos 404, sección UI ausente,
   validaciones aditivas inertes (key ausente = no-op).
5. **No degradar:** contratos de 45/71/72/73/87 intactos; todo aditivo.
6. **3 runtimes (Codex/Claude/Copilot):** no toca el camino de agentes; impacto
   NINGUNO en los tres. Se declara por fase.
7. **Ratchet:** tests backend nuevos registrados en `backend/scripts/run_harness_tests.sh`
   y `.ps1`.
8. **Dominio, no hardcode:** los NOMBRES de procesos (Mul2Bane, IncHost, RSCore,
   RsExtrae) NUNCA se hardcodean en código; viven en el process_catalog del
   client_profile. El código solo conoce `kind` y `publish_group`.

## 4. Modelo de datos (contrato, consumido por F1-F5)

Todo persiste en el client_profile del proyecto (patrón plan 45), bajo keys NUEVAS:

```json
"devops_publication_presets": [
  {
    "name": "quincena-batch",
    "mode": "selection",                    // "selection" | "todo"
    "process_names": ["Mul2Bane", "IncHost"],  // SOLO mode=selection; orden irrelevante (manda el catálogo)
    "groups": ["batch"],                     // filtro opcional: subset de {"batch","agenda"}; [] = sin filtro
    "target": "gitlab"                       // "ado" | "gitlab" (default UI: "gitlab")
  },
  { "name": "todo-completo", "mode": "todo", "groups": [], "target": "gitlab" }
],
"devops_publication_settings": {
  "step_templates": {                        // plantilla de script por kind del catálogo
    "entry":      "echo \"[stacky] publicar {process_name} (entry)\"",
    "processing": "echo \"[stacky] publicar {process_name} (processing)\"",
    "output":     "echo \"[stacky] publicar {process_name} (output)\"",
    "default":    "echo \"[stacky] publicar {process_name}\""
  }
}
```

Y un campo NUEVO OPCIONAL por entrada del process_catalog existente:
`"publish_group": "batch" | "agenda"` (ausente = sin grupo; se tolera, plan 45 tolera
borradores). "Batch" y "agenda" son GRUPOS DE PUBLICACIÓN, NO el `kind` existente
(`entry/processing/output`, `client_profile.py:57`): un proceso tiene un kind (rol en
el flujo de datos) Y opcionalmente un grupo (cadencia de publicación).

**Semántica de resolución (F1, determinista):**
- `mode="todo"` ⇒ candidatos = TODAS las entradas del catálogo. `mode="selection"` ⇒
  candidatos = entradas cuyo `name` ∈ `process_names` (los names no encontrados se
  reportan en `unknown_processes`, NO abortan).
- Filtro `groups`: si `groups` no vacío ⇒ quedan solo candidatos con
  `publish_group` ∈ `groups`. Si `groups == []` ⇒ sin filtro (entra todo, con o sin grupo).
- Orden del pipeline: stages por kind en orden canónico del flujo de carga
  **entry → processing → output** (Mul2Bane→IncHost/RSCore→RsExtrae); dentro de cada
  stage, un job por proceso preservando el ORDEN DEL CATÁLOGO. Kind ausente/desconocido
  ⇒ stage final `otros`.
- Script del step: `step_templates[kind]` si existe, sino `step_templates["default"]`,
  sino el literal `echo "[stacky] publicar {process_name}"`. Sustitución: SOLO el
  placeholder `{process_name}` (reemplazo de string simple, NO `str.format` — evita
  KeyError con llaves en comandos reales).

## 5. Fases

> Comandos de test: idénticos al plan 87 §F4 (pytest por archivo con
> `backend/.venv/Scripts/python.exe` desde `Stacky Agents/backend`; frontend
> `npx tsc --noEmit` + `npx vitest run <archivo>` solo TS puro).

### F0 — Flag `STACKY_DEVOPS_PUBLICATIONS_ENABLED`

**Objetivo:** alta correcta de la flag en las 4 patas, colgada de la del panel.

**Archivos a editar (mismos 3 del plan 87 F0, misma mecánica):**
1. `Stacky Agents/backend/config.py`: junto a `STACKY_DEVOPS_PANEL_ENABLED` (alta del
   plan 87 F0; si se implementan juntos, contiguas):
   ```python
   STACKY_DEVOPS_PUBLICATIONS_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_PUBLICATIONS_ENABLED", "false"
   ).strip().lower() == "true"
   ```
2. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CATEGORY_KEYS["devops"]`: agregar
     `"STACKY_DEVOPS_PUBLICATIONS_ENABLED",  # Plan 88 — publicaciones parametrizables de procesos`.
   - `FlagSpec` nuevo junto al del plan 87:
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_PUBLICATIONS_ENABLED",
         type="bool",
         description="Seccion Publicaciones del panel DevOps: materializa presets de procesos como pipelines.",
         env_only=False,
         requires="STACKY_DEVOPS_PANEL_ENABLED",
     )
     ```
     ⚠️ SIN `default=`, SIN `reserved=` (consumidor real en F3).
3. `Stacky Agents/backend/services/harness_flags_help.py`: entrada `PlainHelp` para la
   key (modelo: la de `STACKY_PIPELINE_GENERATOR_ENABLED`, línea 595).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_publications_flag.py`:
- `test_f0_flag_in_registry`: key en `FLAG_REGISTRY`, `env_only is False`,
  `requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_f0_flag_in_category_devops`: key en `_CATEGORY_KEYS["devops"]`.
- `test_f0_config_default_off`: `config.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED is False`.
- `test_f0_flag_has_plain_help`: key presente en el dict de `harness_flags_help.py`.
- No-regresión: correr también `tests/test_harness_flags.py` y `tests/test_flag_wiring.py`.

**Ratchet:** registrar el archivo en ambos scripts.
**Criterio binario:** 4 tests nuevos + 2 meta verdes; default OFF.
**Flag:** `STACKY_DEVOPS_PUBLICATIONS_ENABLED` (default OFF).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno (opt-in).

### F1 — Materializador PURO `services/publication_spec.py` (corazón del plan)

**Objetivo:** función pura y determinista `preset + catálogo (+ settings) → dict PipelineSpec`.

**Archivo NUEVO:** `Stacky Agents/backend/services/publication_spec.py`
```python
"""publication_spec.py — Plan 88. PURO: sin I/O, sin config, sin flags.
Convierte un preset de publicación + process_catalog en un dict PipelineSpec
(el mismo shape que consume dict_to_spec, services/pipeline_spec.py:69)."""

_KIND_ORDER = ("entry", "processing", "output")   # flujo canónico de carga
_FALLBACK_STAGE = "otros"                          # kind ausente/desconocido
_DEFAULT_TEMPLATE = 'echo "[stacky] publicar {process_name}"'
_ALLOWED_GROUPS = ("batch", "agenda")

def resolve_processes(preset: dict, catalog: list[dict]) -> tuple[list[dict], list[str]]:
    """(procesos_resueltos_en_orden_de_catalogo, unknown_processes).
    mode='todo' -> todo el catálogo; mode='selection' -> por name (case-sensitive).
    Luego filtro groups (si no vacío, exige publish_group ∈ groups).
    Entradas sin 'name' (string no vacío) se ignoran silenciosamente."""

def _script_for(entry: dict, settings: dict | None) -> str:
    """step_templates[kind] > step_templates['default'] > _DEFAULT_TEMPLATE.
    Sustituye SOLO '{process_name}' con str.replace (NUNCA str.format)."""

def build_publication_spec(preset: dict, catalog: list[dict],
                           settings: dict | None = None) -> dict:
    """Retorna {'spec': <dict PipelineSpec>, 'resolved': [names], 'unknown_processes': [names]}.
    spec['name'] = 'publicacion-' + slug(preset['name']) (slug: mismo regex que
    api/pipeline_generator.py:27-31 _slug, copiar la función — 3 líneas, NO importarla
    de api para mantener services sin dependencia de api).
    Stages: por kind en _KIND_ORDER + _FALLBACK_STAGE al final; SOLO stages no vacíos.
    Cada stage: {'name': kind, 'jobs': [...]}; un job por proceso:
      {'name': 'publicar-' + slug(name), 'steps': [{'name': 'publicar', 'script': _script_for(...)}]}.
    Sin procesos resueltos -> spec con stages=[] (inválido a propósito: _validate_spec
    lo rechaza aguas abajo; este módulo NO valida, igual que dict_to_spec)."""
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_publication_spec.py`
(fixture catálogo estilo Pacífico, SOLO en el test, nunca en código de producción):
```python
_CATALOG = [
    {"name": "Mul2Bane", "kind": "entry",      "publish_group": "batch"},
    {"name": "IncHost",  "kind": "processing", "publish_group": "batch"},
    {"name": "RSCore",   "kind": "processing", "publish_group": "batch"},
    {"name": "RsExtrae", "kind": "output",     "publish_group": "batch"},
    {"name": "AgendaX",  "kind": "processing", "publish_group": "agenda"},
    {"name": "SinGrupo", "kind": "output"},
]
```
- `test_f1_todo_includes_everything`: `mode="todo", groups=[]` ⇒ resolved = los 6, en
  orden de catálogo dentro de cada stage; stages = `["entry","processing","output"]`.
- `test_f1_todo_is_dynamic`: mismo preset, catálogo con 1 entrada más ⇒ resolved crece
  (criterio "TODO dinámico").
- `test_f1_groups_filter_batch`: `mode="todo", groups=["batch"]` ⇒ resolved = 4
  (AgendaX y SinGrupo excluidos — SinGrupo no tiene publish_group).
- `test_f1_groups_filter_agenda`: `groups=["agenda"]` ⇒ solo AgendaX.
- `test_f1_selection_by_name_with_unknown`: `mode="selection",
  process_names=["RSCore","NoExiste","Mul2Bane"]` ⇒ resolved = ["Mul2Bane","RSCore"]
  (orden de CATÁLOGO, no del preset); `unknown_processes == ["NoExiste"]`.
- `test_f1_stage_order_canonical`: stages en orden entry→processing→output; job de
  Mul2Bane en stage "entry"; RsExtrae en "output".
- `test_f1_unknown_kind_goes_otros`: entrada con `kind="zzz"` ⇒ stage "otros" al final.
- `test_f1_template_per_kind_and_placeholder`: settings con
  `step_templates={"entry": "deploy-entry {process_name} --now"}` ⇒ script del step de
  Mul2Bane == `"deploy-entry Mul2Bane --now"`; RSCore (sin template processing) usa
  `_DEFAULT_TEMPLATE` con el nombre sustituido.
- `test_f1_braces_in_template_safe`: template `"run {process_name} ${VAR} {otra}"` ⇒
  `{otra}` y `${VAR}` quedan LITERALES (prueba anti-str.format).
- `test_f1_spec_renders_via_plan73`: el spec resultante pasa por
  `dict_to_spec(result["spec"]).validate() == []` y `to_ado_yaml` + `to_gitlab_yaml`
  no lanzan (integración con el motor real, sin mocks).
- `test_f1_empty_resolution_invalid_spec`: preset selection con names inexistentes ⇒
  `resolved == []` y `dict_to_spec(spec).validate()` devuelve errores (no explota).
- `test_f1_pure_no_mutation`: el catálogo y el preset de entrada NO se mutan
  (comparar deepcopy previo).

**Ratchet:** registrar el archivo.
**Criterio binario:** 12 tests verdes.
**Flag:** ninguna (módulo puro sin consumidores hasta F3 ⇒ byte-idéntico).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F2 — Validación aditiva en client_profile (presets, settings, publish_group)

**Objetivo:** persistencia segura por UI de presets/settings, y el campo
`publish_group` en el catálogo, sin romper el PUT existente.

**Archivo a editar:** `Stacky Agents/backend/api/client_profile.py`:
1. Constante nueva junto a `ALLOWED_PROCESS_KINDS` (línea 57):
   `ALLOWED_PUBLISH_GROUPS = {"batch", "agenda"}`.
2. DENTRO del loop de validación de `process_catalog` existente (líneas 144-156),
   agregar al final del cuerpo del loop (aditivo, mismo criterio de tolerancia que
   `kind`):
   ```python
   pg = item.get("publish_group")
   if pg and pg not in ALLOWED_PUBLISH_GROUPS:
       return jsonify({"ok": False, "error": "invalid_publish_group",
                       "value": pg, "allowed": sorted(ALLOWED_PUBLISH_GROUPS),
                       "index": idx}), 400
   ```
3. Después del bloque de `devops_pipeline_drafts` (plan 87 F2) y antes de
   `previous = load_client_profile(...)` (línea 158 pre-plan-87), validación de las 2
   keys nuevas (key ausente = no-op literal):
   ```python
   # Plan 88 F2 — presets de publicación (aditivo).
   presets = profile.get("devops_publication_presets")
   if presets is not None:
       if not isinstance(presets, list):
           return jsonify({"ok": False, "error": "devops_publication_presets debe ser una lista."}), 400
       for idx, p in enumerate(presets):
           if not isinstance(p, dict) or not isinstance(p.get("name"), str) or not p.get("name").strip():
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].name es obligatorio."}), 400
           if p.get("mode") not in ("selection", "todo"):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].mode debe ser 'selection' o 'todo'."}), 400
           if p.get("mode") == "selection" and not isinstance(p.get("process_names"), list):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].process_names debe ser una lista en mode=selection."}), 400
           groups = p.get("groups", [])
           if not isinstance(groups, list) or any(g not in ALLOWED_PUBLISH_GROUPS for g in groups):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].groups: subset de {sorted(ALLOWED_PUBLISH_GROUPS)}."}), 400
           if p.get("target") not in (None, "ado", "gitlab"):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].target debe ser 'ado' o 'gitlab'."}), 400
   # Plan 88 F2 — settings de publicación (aditivo).
   pub_settings = profile.get("devops_publication_settings")
   if pub_settings is not None:
       if not isinstance(pub_settings, dict):
           return jsonify({"ok": False, "error": "devops_publication_settings debe ser un objeto."}), 400
       tpls = pub_settings.get("step_templates")
       if tpls is not None:
           if not isinstance(tpls, dict) or any(
               k not in ("entry", "processing", "output", "default") or not isinstance(v, str)
               for k, v in tpls.items()
           ):
               return jsonify({"ok": False, "error": "step_templates: keys en {entry,processing,output,default} y valores string."}), 400
   ```
   (Nombres duplicados de preset NO se validan acá: la UI usa el último; documentado.)

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_presets_validation.py`
(mismo setup de PUT exitoso que el test de plan 87 F2):
- `test_f2_absent_keys_noop`: PUT sin las keys nuevas ⇒ 200.
- `test_f2_preset_bad_mode_400`, `test_f2_preset_no_name_400`,
  `test_f2_selection_without_names_400`, `test_f2_bad_group_400`,
  `test_f2_bad_target_400`.
- `test_f2_publish_group_invalid_400`: catálogo con `publish_group="mensual"` ⇒ 400
  con `error == "invalid_publish_group"`.
- `test_f2_publish_group_absent_tolerated`: catálogo sin el campo ⇒ 200 (backward compat).
- `test_f2_valid_roundtrip`: PUT con presets+settings+publish_group válidos ⇒ 200 y el
  GET devuelve las 3 keys intactas.
- `test_f2_bad_template_key_400`: `step_templates={"deploy": "x"}` ⇒ 400.

**Ratchet:** registrar. **Criterio binario:** 10 tests verdes + tests existentes de
client_profile y los del plan 87 F2 verdes.
**Flag:** ninguna (aditivo inerte). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Endpoint `POST /api/devops/publications/materialize` (solo-lectura)

**Objetivo:** exponer el materializador con datos reales del proyecto; cero efectos.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` (creado en plan 87 F1):
```python
@bp.post("/publications/materialize")
def materialize_publication_route():
    """Preset -> dict PipelineSpec. SOLO-LECTURA (no commitea, no dispara)."""
    if not getattr(_config.config, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False):
        abort(404)  # guard per-request (patrón pipeline_generator.py:37)
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    preset_name = body.get("preset_name")
    if not project or not preset_name:
        return jsonify({"error": "project y preset_name son obligatorios"}), 400
    profile = load_client_profile(project) or {}   # mismo loader que client_profile.py
    presets = profile.get("devops_publication_presets") or []
    preset = next((p for p in presets if p.get("name") == preset_name), None)
    if preset is None:
        return jsonify({"error": f"preset '{preset_name}' no existe", "kind": "preset_not_found"}), 404
    result = build_publication_spec(
        preset,
        profile.get("process_catalog") or [],
        profile.get("devops_publication_settings"),
    )
    return jsonify(result)   # {'spec':..., 'resolved':[...], 'unknown_processes':[...]}
```
Imports nuevos arriba del archivo: `from services.publication_spec import
build_publication_spec` y el loader de client_profile (usar EXACTAMENTE el mismo
símbolo/módulo que importa `api/client_profile.py:158` — verificar el nombre real de
`load_client_profile` y su módulo con grep antes de escribir).
Además, en `devops_health_route` (plan 87 F1), agregar al JSON:
`"publications_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False))`
(aditivo; el contrato del plan 87 no se rompe: solo se agrega una key).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_materialize_endpoint.py`
(fixtures `app_flag_on`/`app_flag_off` sobre `STACKY_DEVOPS_PUBLICATIONS_ENABLED`,
patrón `test_plan73_generator_endpoint.py:8-31`; mockear el loader de client_profile
con `unittest.mock.patch` EN EL MÓDULO `api.devops` — patrón lazy-import del repo):
- `test_f3_flag_off_404`.
- `test_f3_missing_params_400`: sin `project` ⇒ 400; sin `preset_name` ⇒ 400.
- `test_f3_preset_not_found_404`: profile sin ese preset ⇒ 404 con
  `kind == "preset_not_found"`.
- `test_f3_materialize_ok`: profile mockeado con `_CATALOG` de F1 + preset todo ⇒ 200,
  `resolved` == 6 names, `spec.name` empieza con `"publicacion-"`.
- `test_f3_readonly_no_writes`: el mock del saver de client_profile NO fue llamado
  (assert_not_called) — materializar jamás escribe.
- `test_f3_health_exposes_publications_enabled`: GET `/api/devops/health` contiene la
  key `publications_enabled` (bool).

**Ratchet:** registrar. **Criterio binario:** 6 tests verdes + los del plan 87 F1 verdes.
**Flag:** `STACKY_DEVOPS_PUBLICATIONS_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: modelo puro de presets + API client

**Objetivo:** lógica de edición de presets pura y testeable; llamadas tipadas.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/presetsModel.ts`
- Tipos espejo EXACTOS del contrato §4:
  ```ts
  export type PublishGroup = "batch" | "agenda";
  export interface PublicationPreset { name: string; mode: "selection" | "todo"; process_names?: string[]; groups: PublishGroup[]; target?: "ado" | "gitlab"; }
  export interface PublicationSettings { step_templates?: Partial<Record<"entry" | "processing" | "output" | "default", string>>; }
  ```
- Funciones puras inmutables: `emptyPreset(): PublicationPreset` (`{name:"", mode:"todo",
  groups:[], target:"gitlab"}`); `upsertPreset(list, preset)` (reemplaza por `name`, o
  agrega); `removePreset(list, name)`; `validatePresetLocal(preset): string[]`
  (mismas reglas que F2, para feedback inmediato en UI: name vacío, mode inválido,
  selection sin process_names, groups fuera de allowlist).
- `resolvePreview(preset, catalog): {resolved: string[]; excluded: string[]}` — espejo
  TS de `resolve_processes` de F1 (misma semántica, para mostrar en vivo qué entra
  ANTES de llamar al backend; la fuente de verdad sigue siendo el backend).

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` — extender el
namespace `DevOps` del plan 87 F3:
```ts
materializePublication: (project: string, presetName: string) =>
  /* POST /devops/publications/materialize {project, preset_name} →
     {spec: object; resolved: string[]; unknown_processes: string[]} | {error, kind} */
```

**Tests PRIMERO** — `Stacky Agents/frontend/src/devops/presetsModel.test.ts` (vitest TS puro):
- `upsert_replaces_by_name_immutable`; `remove_absent_noop`;
- `validate_selection_without_names_fails`; `validate_todo_ok`;
- `resolvePreview_matches_backend_semantics`: con el `_CATALOG` literal de F1 (copiado
  como fixture TS), preset `{mode:"todo", groups:["batch"]}` ⇒ resolved = los 4 de
  batch, excluded = ["AgendaX","SinGrupo"] (paridad semántica con
  `test_f1_groups_filter_batch`).
- `resolvePreview_selection_unknown`: paridad con `test_f1_selection_by_name_with_unknown`.

Comando: `npx vitest run src/devops/presetsModel.test.ts`.
**Criterio binario:** vitest verde (6 tests) + `npx tsc --noEmit` 0 errores.
**Flag:** ninguna (código sin montar hasta F5).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F5 — Frontend: sección "Publicaciones" en el panel DevOps

**Objetivo:** UI completa del flujo preset → materializar → preview YAML → commit
HITL → trigger HITL, montada como sección del plan 87.

**Archivos NUEVOS** (en `Stacky Agents/frontend/src/components/devops/`):
1. `PublicationsSection.tsx` — layout 2 columnas:
   - Izquierda: lista de presets (de `devops_publication_presets` vía los endpoints
     client-profile existentes, igual que los drafts del plan 87 F5), botones
     crear/editar/borrar (usa `presetsModel.ts`; guardar = PUT client-profile con la
     lista actualizada), editor de preset: nombre; radio mode (selection/todo);
     checklist de procesos del `process_catalog` (solo mode=selection); checkboxes de
     grupos batch/agenda; select target. Debajo, editor de `step_templates` (4
     textareas etiquetadas entry/processing/output/default con hint del placeholder
     `{process_name}`).
   - Derecha: "Vista previa de resolución" en vivo (`resolvePreview`) con la lista de
     procesos que entran/salen; botón **"Materializar"** ⇒
     `DevOps.materializePublication` ⇒ muestra `resolved`/`unknown_processes` y pasa
     el `spec` recibido a los componentes REUSADOS del plan 87 F5:
     `PipelineYamlPreview` (preview ADO+GitLab vía `/api/pipeline-generator/preview`),
     `CommitPipelineModal` (HITL checkbox ⇒ `confirm:true`) y
     `TriggerPipelineSection` (HITL plan 72; visible solo si health da
     `trigger_enabled:true`). Si `unknown_processes` no vacío ⇒ warning visible
     listándolos.
   - Si el health da `publications_enabled:false` ⇒ la sección entera se reemplaza por
     el mensaje "Activá STACKY_DEVOPS_PUBLICATIONS_ENABLED (Configuración → Arnés,
     categoría DevOps)" (patrón MigratorPage.tsx:35-47).
2. Además: en la checklist de procesos y el editor del catálogo YA existente del plan
   45 (buscar el componente que edita `process_catalog` en
   `frontend/src/components/` — grep `process_catalog` — y SOLO SI existe un editor de
   entradas), agregar el select opcional `publish_group` (vacío/batch/agenda). Si no
   existe editor de entradas, NO crearlo: el publish_group se edita vía el JSON del
   client_profile como hasta ahora, y la sección Publicaciones muestra el grupo como
   badge de solo lectura. (Decisión binaria verificable: existe editor ⇒ select;
   no existe ⇒ badge.)

**Archivo a editar:** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — agregar a
`DEVOPS_SECTIONS` (punto de extensión del plan 87 F4):
```ts
{ id: "publicaciones", label: "Publicaciones", render: () => <PublicationsSection /> },
```
Gating fino: `PublicationsSection` se auto-oculta con `publications_enabled:false`
(el health ya viene del contexto de DevOpsPage; pasarlo por prop).

**Tests:** lógica cubierta en F4 (vitest). Gate componentes = `npx tsc --noEmit`.
**Criterio binario:** `tsc` 0 errores; la sección solo es visible con AMBAS flags ON;
commit/trigger inaccesibles sin confirmación explícita (checkbox/preview HITL —
verificable por código).
**Flag:** `STACKY_DEVOPS_PUBLICATIONS_ENABLED` (+ master del panel vía `requires`).
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in (activar la flag en
Configuración → Arnés); definir presets es USO de la feature, no configuración previa.

### F6 — Cierre: no-regresión + checklist binario

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan88_publications_flag.py tests/test_plan88_publication_spec.py tests/test_plan88_presets_validation.py tests/test_plan88_materialize_endpoint.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_flag.py tests/test_plan87_devops_endpoints.py tests/test_plan87_drafts_validation.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan73_generator_endpoint.py tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest run src/devops/presetsModel.test.ts src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Checklist binario de done:**
- [ ] Flag OFF ⇒ `/api/devops/publications/materialize` 404, sección UI ausente,
      byte-idéntico (no-regresión verde).
- [ ] Preset "TODO" con catálogo de 6 ⇒ pipeline de 3 stages en orden
      entry→processing→output; agrego una entrada al catálogo y re-materializo ⇒ la
      nueva entrada aparece SIN tocar el preset.
- [ ] Preset "solo agenda" excluye los batch (y viceversa).
- [ ] El YAML del preview sale de `to_ado_yaml`/`to_gitlab_yaml` (cero YAML a mano:
      grep de este plan no introduce ningún literal `stages:` fuera de tests).
- [ ] Commit imposible sin checkbox HITL; trigger solo vía flujo HITL plan 72.
- [ ] Archivos de test registrados en ambos scripts de ratchet.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Confundir `kind` (entry/processing/output) con grupo batch/agenda | Campo NUEVO `publish_group` ortogonal + glosario + tests F1/F2 que usan ambos a la vez |
| `str.format` sobre templates con `{}` de shell | Prohibido por contrato (§4) + `test_f1_braces_in_template_safe` |
| Drift semántico entre `resolve_processes` (py) y `resolvePreview` (ts) | Mismos fixtures literales en ambos tests (F1/F4, paridad por casos); backend = fuente de verdad (el spec siempre viene del endpoint) |
| Hardcodear procesos Pacífico en producción | Prohibido (§3.8); solo aparecen en fixtures de test |
| PUT client_profile crece en validaciones y se vuelve frágil | Cada bloque es aditivo, key ausente = no-op, con test explícito de no-op |
| Preset apunta a procesos borrados del catálogo | `unknown_processes` reportado (nunca aborta) + warning en UI |
| Plan 87 no implementado aún | Dependencia declarada arriba; F0-F2 de este plan no dependen de código del 87 (solo F3 toca `api/devops.py` y F5 la página) — orden de implementación lo respeta |

## 7. Fuera de scope (v1)

- Ejecutar la publicación DIRECTO sobre servidores (esto genera/commitea/dispara
  pipelines; el deploy real lo hace el pipeline en el runner de CI).
- Scheduling/cron de publicaciones (violaría HITL; el trigger es siempre manual).
- Grupos de publicación adicionales a batch/agenda (allowlist cerrada v1).
- Plantillas de step por PROCESO individual (v1 es por kind; el escape hatch es editar
  el pipeline resultante en el builder del plan 87).
- Inicialización de ambientes ⇒ plan 3 de la serie (dependerá de éste).

## 8. Glosario

- **Publicación**: deploy de uno o más procesos del catálogo, materializado como
  pipeline CI (nunca ejecución directa desde Stacky).
- **Preset de publicación**: parametrización guardada (qué procesos, qué grupos, qué
  target) en `devops_publication_presets` del client_profile.
- **TODO**: modo de preset que resuelve TODOS los procesos del catálogo (con filtro
  opcional de grupos) al momento de materializar — dinámico por diseño.
- **publish_group**: grupo de publicación (`batch`|`agenda`) de una entrada del
  catálogo; ortogonal al `kind` (`entry`/`processing`/`output` = rol en el flujo de
  datos, `client_profile.py:57`).
- **Materializar**: convertir preset+catálogo en dict PipelineSpec (puro, solo-lectura).
- **process_catalog / client_profile / HITL / FLAG_REGISTRY / ratchet**: ver glosario
  del plan 87 §7.
- **Flujo canónico Pacífico**: Mul2Bane (entry, deja en IN_) → IncHost (→productivas)
  → RSCore (aplica) → RsExtrae (salida); es el ORIGEN del orden entry→processing→output.

## 9. Orden de implementación

1. F0 — flag (tests meta verdes).
2. F1 — `services/publication_spec.py` puro (12 tests).
3. F2 — validación aditiva client_profile.
4. F3 — endpoint materialize + health key (requiere plan 87 F1 implementado).
5. F4 — `presetsModel.ts` + endpoints.ts (vitest).
6. F5 — `PublicationsSection` + registro en `DEVOPS_SECTIONS` (requiere plan 87 F4/F5).
7. F6 — cierre.

## 10. Definición de Hecho (DoD)

- 32+ tests nombrados (F0:4, F1:12, F2:10, F3:6) verdes por archivo con el venv.
- Vitest F4 verde; `npx tsc --noEmit` 0 errores.
- No-regresión: tests planes 87/73 + meta-tests del arnés verdes.
- Flag OFF ⇒ byte-idéntico; checklist F6 completo.
- Cero YAML generado a mano; cero nombres de procesos hardcodeados en producción.
