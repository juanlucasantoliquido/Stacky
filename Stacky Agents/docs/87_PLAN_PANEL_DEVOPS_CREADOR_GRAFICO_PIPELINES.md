# Plan 87 — Panel DevOps: creador GRÁFICO de pipelines

**Estado:** PROPUESTO
**Fecha:** 2026-07-03
**Serie DevOps:** plan 1 de 3 (base). Los planes siguientes de la serie (publicaciones
parametrizables de procesos batch/agenda/TODO, e inicialización de ambientes) se montan
SOBRE este panel sin refactor.
**Dependencias:** ninguna dentro de la serie (es la base); requiere planes 71/72/73 ya
implementados — VERIFICADO en código:

| Pieza existente | Evidencia (archivo:línea) |
|---|---|
| PipelineSpec/Step/Job/Stage + dict_to_spec + validate | `backend/services/pipeline_spec.py:55,27,36,48,69,112` |
| Renderers to_ado_yaml / to_gitlab_yaml / parse_ado_yaml / parse_gitlab_yaml | `backend/services/pipeline_renderers.py:23,126,194,251` |
| POST /api/pipeline-generator/preview (puro) | `backend/api/pipeline_generator.py:34` |
| POST /api/pipeline-generator/commit (HITL confirm=True, guard flag) | `backend/api/pipeline_generator.py:52,59-60,37,55` |
| RepoWriter factory | `backend/services/repo_writer.py:30` |
| Protocol CIProvider + factory get_ci_provider | `backend/services/ci_provider.py:83,94,107` |
| Adapters CI ADO/GitLab | `backend/services/ado_ci_provider.py:31`, `backend/services/gitlab_ci_provider.py:62` |
| Trigger/monitor HITL /api/ci/... | `backend/api/ci.py:26,76,139,174` |
| Patrón de página nueva gated por flag | `frontend/src/pages/MigratorPage.tsx:15`, `frontend/src/App.tsx:57-58,82-86,213-221,234` |
| Persistencia editable por UI en client_profile | `backend/api/client_profile.py:94,127,138-156` |

---

## 1. Objetivo + KPI

Crear la sección **DevOps** de Stacky: una página nueva de UI donde el operador arma
pipelines de forma **visual** (stages → jobs → steps como bloques con propiedades
editables), ve el **preview del YAML** resultante para ADO y GitLab en vivo, y — con
confirmación explícita — lo **commitea al repo** y lo **dispara/monitorea**. El editor
gráfico NO genera YAML por su cuenta: produce un dict `PipelineSpec` y reusa al 100%
los endpoints del plan 73 (`/preview`, `/commit`) y del plan 72 (`/api/ci/...`).

**KPI / impacto esperado:**
- El operador crea y previewea un pipeline válido (1 stage / 1 job / 1 step) en < 2
  minutos **sin escribir una línea de YAML**.
- 0 líneas de YAML escritas a mano; 100% del YAML sale de `to_ado_yaml`/`to_gitlab_yaml`.
- Puede además **importar** un YAML existente (ADO o GitLab) al editor gráfico
  (reusa `parse_ado_yaml`/`parse_gitlab_yaml`) para editarlo visualmente.
- Deja el contenedor extensible (registro de secciones) para los planes 2 y 3 de la
  serie: agregar una sección DevOps nueva = 1 entrada en un array + 1 componente.

## 2. Por qué ahora / gap que cierra

Los planes 71/72/73 construyeron TODO el motor (spec puro, renderers bidireccionales,
commit HITL, trigger/monitor) pero la única UI es inexistente: hoy el operador tendría
que hacer POSTs a mano con JSON crudo. El motor está pagado y sin volante. Este plan
pone el volante: valor alto, costo bajo (casi todo es frontend + 2 endpoints finos de
lectura/parseo), riesgo bajo (cero cambios de contrato en lo existente).

## 3. Principios y guardarraíles (NO negociables)

1. **Human-in-the-loop:** NADA se commitea ni se dispara sin acción explícita del
   operador. Preview siempre disponible antes de commit. El commit exige tildar un
   checkbox de confirmación en el modal (que se traduce en `confirm: true` del endpoint
   existente, `api/pipeline_generator.py:59-60`). El trigger reusa el HITL del plan 72.
2. **Mono-operador, sin auth real:** ninguna noción de roles/permiso.
3. **Flags editables por UI, default OFF:** flag master nueva
   `STACKY_DEVOPS_PANEL_ENABLED` en `FLAG_REGISTRY` (`services/harness_flags.py`),
   categoría nueva `devops`, `env_only=False` (⇒ alta obligatoria en `config.py`,
   gotcha plan 81). **NO pasar `default=False` explícito** en el `FlagSpec` (rompe
   `test_default_known_only_for_curated`; solo `_CURATED_DEFAULTS_ON` puede).
4. **Byte-idéntico con flag OFF:** con `STACKY_DEVOPS_PANEL_ENABLED=false` la tab
   DevOps NO aparece, los endpoints nuevos devuelven `flag_enabled:false` (health) o
   404 (parse-yaml), y ningún flujo existente cambia ni un byte.
5. **No degradar lo existente:** los endpoints del plan 73 y del plan 72 NO cambian de
   contrato. Toda extensión es aditiva (endpoints nuevos bajo `/api/devops/...`).
6. **3 runtimes (Codex / Claude Code CLI / GitHub Copilot):** este plan NO toca el
   camino de ejecución de agentes; es UI + endpoints Flask. Impacto por runtime:
   NINGUNO en los tres (paridad trivial). Se declara por fase igualmente.
7. **Cero trabajo extra al operador:** opt-in (flag OFF). Sin pasos manuales nuevos.
8. **Ratchet de tests:** todo archivo de test backend nuevo se registra en
   `backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`
   (`HARNESS_TEST_FILES`), o el meta-test del plan 49 F4 falla.
9. **Ayuda llana (plan 86):** toda flag nueva necesita su entrada `PlainHelp` en
   `services/harness_flags_help.py` (hay meta-test de cobertura).

## 4. Fases

> Comando de tests backend (por archivo, con el venv del repo — la suite completa está
> contaminada, plan 49):
> `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>" -q`
> ejecutado desde `Stacky Agents/backend` (o con `cd` previo; los tests asumen cwd=backend).
> Gate frontend: `npx tsc --noEmit` en `Stacky Agents/frontend` (0 errores). Vitest solo
> para TS puro (no hay `@testing-library/react`; NO escribir tests de componentes React).

### F0 — Flag master + categoría `devops` (backend, sin comportamiento)

**Objetivo:** dar de alta `STACKY_DEVOPS_PANEL_ENABLED` correctamente en las 4 patas
(config, registry, help, categoría) sin romper ningún meta-test.

**Archivos a editar:**
1. `Stacky Agents/backend/config.py` — junto a `STACKY_PIPELINE_GENERATOR_ENABLED`
   (línea ~851), agregar:
   ```python
   STACKY_DEVOPS_PANEL_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_PANEL_ENABLED", "false"
   ).strip().lower() == "true"
   ```
   (copiar la forma EXACTA de parseo de la flag vecina línea 851-852).
2. `Stacky Agents/backend/services/harness_flags.py`:
   - En `_CATEGORY_KEYS` agregar la categoría NUEVA (después de
     `"migrador_ado_gitlab"`, línea ~170):
     ```python
     "devops": (
         "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 87 — panel DevOps: creador gráfico de pipelines
     ),
     ```
   - Agregar el `CategorySpec` de `devops` imitando byte a byte la ESTRUCTURA del de
     `migrador_ado_gitlab` (buscar `migrador_ado_gitlab` en el dict de categorías;
     copiar todos los campos que tenga — `description`, `tier`, `intent`, etc. del
     plan 78 — con valores propios: descripción "Panel DevOps: creación gráfica de
     pipelines y operaciones de publicación", tier/intent = los mismos valores que
     use `migrador_ado_gitlab`).
   - Agregar el `FlagSpec` (cerca del de `STACKY_PIPELINE_GENERATOR_ENABLED`,
     línea ~1912):
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_PANEL_ENABLED",
         type="bool",
         description="Muestra la seccion DevOps en la UI (creador grafico de pipelines).",
         env_only=False,
         requires="STACKY_PIPELINE_GENERATOR_ENABLED",  # Plan 82 — el preview/commit viven detras de esa flag
     )
     ```
     ⚠️ SIN `default=` (gotcha `_CURATED_DEFAULTS_ON`). ⚠️ SIN `reserved=` (tiene
     consumidor real en F1). Ajustar kwargs posicionales/nombrados al constructor real
     de `FlagSpec` (`services/harness_flags.py:21-41`).
3. `Stacky Agents/backend/services/harness_flags_help.py` — agregar la entrada
   `PlainHelp` para `STACKY_DEVOPS_PANEL_ENABLED` imitando la estructura de
   `STACKY_PIPELINE_GENERATOR_ENABLED` (línea 595): texto llano, qué pasa ON/OFF,
   ejemplo cotidiano.

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan87_devops_flag.py`:
- `test_f0_flag_in_registry`: `STACKY_DEVOPS_PANEL_ENABLED` está en `FLAG_REGISTRY`,
  `env_only is False`, `requires == "STACKY_PIPELINE_GENERATOR_ENABLED"`.
- `test_f0_flag_in_category_devops`: la key está en `_CATEGORY_KEYS["devops"]`.
- `test_f0_config_default_off`: `import config; config.config.STACKY_DEVOPS_PANEL_ENABLED is False`
  (sin env var seteada).
- `test_f0_flag_has_plain_help`: la key existe en el dict de ayuda de
  `harness_flags_help.py`.
- Correr TAMBIÉN (no-regresión de meta-tests):
  `python -m pytest tests/test_harness_flags.py tests/test_flag_wiring.py -q`.

**Registro ratchet:** agregar `tests/test_plan87_devops_flag.py` a
`scripts/run_harness_tests.sh` y `scripts/run_harness_tests.ps1`.

**Criterio binario:** los 4 tests nuevos + `test_harness_flags.py` + `test_flag_wiring.py`
pasan. Flag OFF por default.
**Flag:** `STACKY_DEVOPS_PANEL_ENABLED` (default OFF).
**Runtimes:** sin impacto (Codex/Claude/Copilot idénticos).
**Trabajo del operador:** ninguno (opt-in, default off).

### F1 — Backend: blueprint `/api/devops` (health + parse-yaml)

**Objetivo:** dar al frontend (a) un health para gatear la tab (patrón migrador) y
(b) un endpoint PURO para importar YAML existente al editor gráfico.

**Archivo NUEVO:** `Stacky Agents/backend/api/devops.py`
```python
"""api/devops.py — Blueprint del panel DevOps (Plan 87).
url_prefix="/devops" → rutas finales /api/devops/... (NO poner /api/ en el prefix,
ver FIX C2 del plan 73 en api/pipeline_generator.py:7-8)."""
from dataclasses import asdict
from flask import Blueprint, jsonify, request, abort
import config as _config
from services.pipeline_renderers import parse_ado_yaml, parse_gitlab_yaml

bp = Blueprint("devops", __name__, url_prefix="/devops")

@bp.get("/health")
def devops_health_route():
    """SIEMPRE 200 (la UI lo usa para decidir si muestra la tab, patrón /api/migrator/health)."""
    cfg = _config.config
    return jsonify({
        "flag_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PANEL_ENABLED", False)),
        "generator_enabled": bool(getattr(cfg, "STACKY_PIPELINE_GENERATOR_ENABLED", False)),
        "trigger_enabled": bool(getattr(cfg, "STACKY_PIPELINE_TRIGGER_ENABLED", False)),
    })

@bp.post("/parse-yaml")
def parse_yaml_route():
    """YAML (ado|gitlab) → dict PipelineSpec para hidratar el editor. PURO, sin I/O."""
    if not getattr(_config.config, "STACKY_DEVOPS_PANEL_ENABLED", False):
        abort(404)  # guard per-request, mismo patrón que pipeline_generator.py:37
    body = request.get_json(silent=True) or {}
    source = body.get("source")           # "ado" | "gitlab"
    yaml_str = body.get("yaml") or ""
    if source not in ("ado", "gitlab") or not yaml_str.strip():
        return jsonify({"error": "source ('ado'|'gitlab') y yaml son obligatorios"}), 400
    try:
        spec = parse_ado_yaml(yaml_str) if source == "ado" else parse_gitlab_yaml(yaml_str)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"spec": asdict(spec)})
```

**Registro:** en `Stacky Agents/backend/api/__init__.py`, imitar EXACTAMENTE las dos
líneas del plan 73 (`api/__init__.py:43` y `:88`):
```python
from .devops import bp as devops_bp  # Plan 87 — panel DevOps
...
api_bp.register_blueprint(devops_bp)  # Plan 87 — url_prefix="/devops" → /api/devops/...
```

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan87_devops_endpoints.py`
(copiar los fixtures `app_flag_on`/`app_flag_off` de
`tests/test_plan73_generator_endpoint.py:8-31`, cambiando la key a
`STACKY_DEVOPS_PANEL_ENABLED`):
- `test_f1_health_always_200_flag_off`: GET `/api/devops/health` con flag OFF → 200 y
  `flag_enabled is False`.
- `test_f1_health_flag_on`: con flag ON → 200 y `flag_enabled is True`; el JSON
  contiene `generator_enabled` y `trigger_enabled` (bool).
- `test_f1_parse_yaml_flag_off_404`: POST `/api/devops/parse-yaml` con flag OFF → 404.
- `test_f1_parse_yaml_roundtrip_gitlab`: flag ON; tomar `_VALID_SPEC` (mismo dict que
  `test_plan73_generator_endpoint.py:34-39`), renderizarlo con
  `to_gitlab_yaml(dict_to_spec(_VALID_SPEC))`, POSTearlo con `source="gitlab"` → 200 y
  `spec["name"] == "my-pipeline"` y `len(spec["stages"]) == 1`.
- `test_f1_parse_yaml_bad_input_400`: flag ON; body sin `yaml` → 400; `source="foo"` → 400;
  yaml malformado (`"::::not yaml"`) → 400 (nunca 500).
- `test_f1_route_registered`: centinela — `create_app()` y assert que
  `"/api/devops/health"` está en `[r.rule for r in app.url_map.iter_rules()]`
  (patrón centinela del plan 74).

**Registro ratchet:** agregar el archivo a ambos scripts de ratchet.

**Criterio binario:** 6 tests verdes; `test_plan73_generator_endpoint.py` sigue verde
(no-regresión de contrato).
**Flag:** `STACKY_DEVOPS_PANEL_ENABLED` (guard per-request en parse-yaml; health sin guard
pero solo informa booleans — mismo trade-off que /api/migrator/health).
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F2 — Persistencia de borradores en client_profile (validación aditiva)

**Objetivo:** que el operador pueda guardar/retomar borradores de pipeline por
proyecto SIN backend nuevo de storage: se reusa el client_profile editable por UI
(plan 45), bajo la key nueva `devops_pipeline_drafts`.

**Contrato de datos** (lo consume el frontend en F4/F5):
```json
"devops_pipeline_drafts": [
  {"name": "publicacion-batch", "spec": { ...dict PipelineSpec... }, "updated_at": "2026-07-03T12:00:00Z"}
]
```

**Archivo a editar:** `Stacky Agents/backend/api/client_profile.py` — en
`put_client_profile` (línea 127), DESPUÉS del bloque de validación de
`process_catalog` (líneas 138-156) y ANTES de `previous = load_client_profile(...)`
(línea 158), agregar validación aditiva con la MISMA filosofía ("solo se valida lo
que el operador envía; si la key no viene, no hay cambio"):
```python
# Plan 87 F2 — validar devops_pipeline_drafts (aditivo; ausente = no-op).
drafts = profile.get("devops_pipeline_drafts")
if drafts is not None:
    if not isinstance(drafts, list):
        return jsonify({"ok": False, "error": "devops_pipeline_drafts debe ser una lista."}), 400
    for idx, d in enumerate(drafts):
        if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not d.get("name").strip():
            return jsonify({"ok": False, "error": f"devops_pipeline_drafts[{idx}].name es obligatorio (string no vacio)."}), 400
        if not isinstance(d.get("spec"), dict):
            return jsonify({"ok": False, "error": f"devops_pipeline_drafts[{idx}].spec debe ser un objeto."}), 400
```
NO validar el spec contra `_validate_spec` acá: un borrador PUEDE estar incompleto
(mismo criterio que "kind vacío se tolera (borrador en edición)" del plan 45,
`client_profile.py:148`). La validación dura ocurre en `/preview`//`/commit`.

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan87_drafts_validation.py`:
- `test_f2_absent_key_noop`: PUT de un profile SIN la key → mismo resultado que hoy
  (200/`ok:true` con un profile mínimo válido; usar el patrón de tests existentes de
  client_profile — buscar `put_client_profile` en `tests/` y copiar el setup del test
  más simple que haga PUT exitoso).
- `test_f2_drafts_not_list_400`: `"devops_pipeline_drafts": {}` → 400.
- `test_f2_draft_without_name_400`: `[{"spec": {}}]` → 400.
- `test_f2_draft_without_spec_400`: `[{"name": "x"}]` → 400.
- `test_f2_valid_drafts_persist`: PUT con 1 draft válido → 200; GET
  (`get_client_profile`, `client_profile.py:94`) devuelve la key intacta.
- `test_f2_incomplete_spec_tolerated`: draft con `spec = {"name": "", "stages": []}`
  (inválido para publicar) → 200 (borrador en edición se tolera).

**Registro ratchet:** agregar el archivo a ambos scripts.

**Criterio binario:** 6 tests verdes; los tests existentes de client_profile siguen
verdes (correr el/los archivos `tests/test_*client_profile*.py` que existan).
**Flag:** ninguna (validación aditiva inerte: con flag OFF nadie envía la key ⇒
byte-idéntico).
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Frontend: modelo puro del builder (`specBuilder.ts`) + API client

**Objetivo:** toda la lógica de edición del pipeline como funciones puras testeables
con vitest (TS puro, sin React), y los namespaces de API.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/specBuilder.ts`
- Tipos espejo EXACTOS del contrato de `dict_to_spec` (`pipeline_spec.py:69-107` —
  usar los MISMOS nombres de campo, snake_case incluido):
  ```ts
  export interface StepDraft { name: string; script: string; working_directory?: string | null; condition?: string | null; env: Record<string, string>; }
  export interface JobDraft { name: string; steps: StepDraft[]; image?: string | null; pool_vm_image?: string | null; runner_tags: string[]; variables: Record<string, string>; artifacts: string[]; services: string[]; }
  export interface StageDraft { name: string; jobs: JobDraft[]; condition?: string | null; }
  export interface PipelineSpecDraft { name: string; stages: StageDraft[]; variables: Record<string, string>; trigger_branches: string[]; raw_yaml?: string | null; raw_yaml_target?: "ado" | "gitlab" | null; }
  ```
- Funciones puras (todas inmutables — devuelven copia nueva, nunca mutan):
  `emptySpec(): PipelineSpecDraft` (name:"", stages:[], variables:{}, trigger_branches:[]);
  `addStage(spec)`, `removeStage(spec, si)`, `moveStage(spec, si, dir: -1|1)`;
  `addJob(spec, si)`, `removeJob(spec, si, ji)`, `moveJob(spec, si, ji, dir)`;
  `addStep(spec, si, ji)`, `removeStep(spec, si, ji, sti)`, `moveStep(spec, si, ji, sti, dir)`;
  `updateStage(spec, si, patch)`, `updateJob(spec, si, ji, patch)`, `updateStep(spec, si, ji, sti, patch)`;
  `toSpecDict(spec): object` (limpia nulls opcionales — omite keys con null/undefined —
  para que el JSON matchee lo que `dict_to_spec` espera).
  Índices fuera de rango: devolver el spec SIN cambios (nunca throw).
- Defaults al agregar: `addStage` crea `{name: "stage-" + (n+1), jobs: []}`;
  `addJob` crea `{name: "job-1", steps: [], runner_tags: [], variables: {}, artifacts: [], services: []}`;
  `addStep` crea `{name: "step-1", script: "", env: {}}`.

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` — imitando el
namespace `Migrator` (línea 3008), agregar:
```ts
export const DevOps = {
  health: () => http<{ flag_enabled: boolean; generator_enabled: boolean; trigger_enabled: boolean }>("/devops/health"),
  parseYaml: (source: "ado" | "gitlab", yaml: string) => /* POST /devops/parse-yaml */,
};
export const PipelineGenerator = {
  preview: (spec: object) => /* POST /pipeline-generator/preview → {ado, gitlab} | {errors:[{field,message}]} */,
  commit: (body: object) => /* POST /pipeline-generator/commit (body incluye confirm:true, target, branch, project y el spec) */,
};
```
(usar el helper HTTP EXACTO que ya use `Migrator` en ese archivo — leerlo y copiar la
forma; si ya existiera un namespace para `/ci` reusarlo, si no, agregar
`Ci.trigger/monitor` leyendo las rutas EXACTAS de `backend/api/ci.py:70-180` antes de
escribirlas).

**Tests PRIMERO** — archivo nuevo `Stacky Agents/frontend/src/devops/specBuilder.test.ts`
(vitest TS puro, patrón de los tests TS puros existentes del repo):
- `emptySpec_shape`: emptySpec() tiene stages=[], variables={}, trigger_branches=[].
- `addStage_appends_and_is_immutable`: el spec original NO cambia (`!==` y deep-equal
  al snapshot previo).
- `move_out_of_range_noop`: moveStage(spec, 0, -1) con 1 stage → igual.
- `remove_indices_out_of_range_noop`.
- `nested_add_update`: addStage→addJob→addStep→updateStep(script:"make build") deja el
  script en su lugar y solo ahí.
- `toSpecDict_omits_nullish`: un StepDraft sin condition ⇒ el dict NO tiene la key
  `condition`.
Comando: `npx vitest run src/devops/specBuilder.test.ts` en `Stacky Agents/frontend`.

**Criterio binario:** vitest verde (6 tests) + `npx tsc --noEmit` 0 errores.
**Flag:** ninguna (código muerto hasta F4/F5; tree-shaken; byte-idéntico en runtime).
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F4 — Frontend: página DevOps contenedora extensible + tab gated

**Objetivo:** la tab "DevOps" visible SOLO con flag ON, con un registro de secciones
para que los planes 2 y 3 de la serie agreguen secciones sin tocar el contenedor.

**Archivo NUEVO:** `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — patrón
`MigratorPage.tsx:15-47` (loading → flag OFF mensaje informativo con el nombre de la
flag y dónde activarla → flag ON contenido):
- `const healthQuery = useQuery({ queryKey: ["devops-health"], queryFn: () => DevOps.health(), retry: false });`
- Registro extensible (EXPORTADO para los planes 2/3):
  ```ts
  export interface DevOpsSection { id: string; label: string; render: () => JSX.Element; }
  export const DEVOPS_SECTIONS: DevOpsSection[] = [
    { id: "pipelines", label: "Pipelines", render: () => <PipelineBuilderSection /> },
    // Plan 88 (publicaciones) y Plan 89 (ambientes) agregan entradas ACA, sin refactor.
  ];
  ```
- Sub-tabs internas simples (useState con el id activo; botones por sección).

**Archivo a editar:** `Stacky Agents/frontend/src/App.tsx` — replicar EXACTAMENTE el
patrón migrador en sus 5 puntos:
1. import `DevOpsPage` (junto a línea 13);
2. estado `const [devopsEnabled, setDevopsEnabled] = useState(false);` (junto a :58);
3. en el `useEffect` de :78-86, fetch `/api/devops/health` →
   `setDevopsEnabled(d.flag_enabled === true)` con `.catch(() => setDevopsEnabled(false))`;
4. redirect si tab activa sin flag (junto a :128):
   `else if (tab === "devops" && !devopsEnabled) selectTab("team");`
5. botón de nav condicional (junto a :213-221) + render
   `{tab === "devops" && devopsEnabled && <DevOpsPage />}` (junto a :234).
Además: agregar `"devops"` al tipo `Tab` y a `TAB_PATHS` (buscar la definición de
`TAB_PATHS`/`tabFromPath` en App.tsx o su módulo y agregar la entrada con path
`/devops`, mismo formato que `migrador`).

**Tests:** no hay test runner de componentes (sin `@testing-library/react`).
Gate = `npx tsc --noEmit` 0 errores + verificación manual binaria del criterio.

**Criterio binario:** (a) `tsc` 0 errores; (b) con flag OFF el fetch devuelve
`flag_enabled:false` ⇒ la tab NO se renderiza (verificable en el código: el botón está
dentro de `{devopsEnabled && ...}`); (c) `DEVOPS_SECTIONS` exportado con 1 entrada.
**Flag:** `STACKY_DEVOPS_PANEL_ENABLED` (gatea tab y página).
**Runtimes:** sin impacto.
**Trabajo del operador:** opt-in — activar la flag desde Configuración → Arnés
(HarnessFlagsPanel, categoría "devops"); ningún otro paso.

### F5 — Frontend: PipelineBuilder (bloques + propiedades + preview + import)

**Objetivo:** el editor visual propiamente dicho, 100% sobre `specBuilder.ts` (F3) y
los endpoints existentes.

**Archivos NUEVOS** (en `Stacky Agents/frontend/src/components/devops/`):
1. `PipelineBuilderSection.tsx` — orquesta: estado `spec: PipelineSpecDraft`
   (useState, inicial `emptySpec()`), layout 2 columnas: izquierda árbol de bloques,
   derecha panel de propiedades + preview. Barra superior: nombre del pipeline,
   selector de borrador (carga/guarda `devops_pipeline_drafts` vía los endpoints
   client-profile EXISTENTES — leer las rutas reales de `backend/api/client_profile.py`
   decoradores de :84-127 antes de escribirlas), botón "Importar YAML" (textarea +
   selector ado/gitlab → `DevOps.parseYaml` → hidrata `spec`), botones
   "Preview" / "Commit al repo…" / "Disparar…".
2. `BlockTree.tsx` — render recursivo de stages/jobs/steps como bloques anidados;
   cada bloque: nombre, botones ↑ ↓ ✕ y "+ job"/"+ step" según nivel; click
   selecciona el bloque (estado `selected: {si?, ji?, sti?}`); TODO manipula el spec
   SOLO vía funciones de `specBuilder.ts` (nunca mutación directa).
3. `BlockProperties.tsx` — formulario del bloque seleccionado: Stage(name, condition);
   Job(name, image, pool_vm_image, runner_tags CSV, variables key=value por línea,
   artifacts CSV, services CSV); Step(name, script textarea multilínea,
   working_directory, condition, env key=value por línea). Pipeline (nada
   seleccionado): name, variables, trigger_branches CSV, raw_yaml/raw_yaml_target
   (escape hatch, colapsado bajo "Avanzado").
4. `PipelineYamlPreview.tsx` — botón/auto refresh: `PipelineGenerator.preview(toSpecDict(spec))`;
   200 ⇒ dos `<pre>` lado a lado (Azure DevOps / GitLab CI); 400 con `errors` ⇒ lista
   `field: message` en rojo (contrato exacto: `api/pipeline_generator.py:43`); si el
   health dio `generator_enabled:false`, mostrar aviso "Activá
   STACKY_PIPELINE_GENERATOR_ENABLED (categoría épicas/ADO) para preview/commit" en
   lugar de llamar (el endpoint daría 404, `pipeline_generator.py:37`).
5. `CommitPipelineModal.tsx` — HITL: selector target (`gitlab`; opción `ado`
   deshabilitada con nota "ADO: render-only v1 — commit devuelve 501",
   `pipeline_generator.py:86-88`), input branch (placeholder
   `feature/pipeline-<slug>`, default vacío ⇒ backend deriva,
   `pipeline_generator.py:71`), input project (default: proyecto activo de
   `useWorkbench`, patrón `MigratorPage.tsx:16-17`), checkbox OBLIGATORIO
   "Confirmo el commit de este pipeline al repositorio" que habilita el botón; submit
   ⇒ `PipelineGenerator.commit({...toSpecDict(spec), target, branch, project, confirm: true})`;
   mostrar resultado (éxito con datos del commit / error con `error` y `kind`).
6. `TriggerPipelineSection.tsx` — SOLO si health dio `trigger_enabled:true`: botones
   que llaman las rutas del plan 72 (`/api/ci/...` — leer rutas y payloads EXACTOS de
   `backend/api/ci.py:70-180` antes de implementar) con su preview HITL
   (`trigger_preview_route:139`) antes del trigger real; polling de estado vía
   `monitor_pipeline_route:174`. Si `trigger_enabled:false` ⇒ sección oculta con nota.

**Tests:** lógica ya cubierta en F3 (vitest puro). Componentes: gate `tsc`.
Agregar a `specBuilder.test.ts` (F3) si faltó: `import_hydrates_from_parse_result` —
dado el JSON `{spec}` que devuelve `/api/devops/parse-yaml` (respuesta de
`asdict(PipelineSpec)`), una función `fromParsedSpec(dict): PipelineSpecDraft` en
`specBuilder.ts` lo normaliza (tuplas→arrays ya llegan como arrays por JSON; nulls
preservados) — test con el fixture literal del roundtrip de F1.

**Criterio binario:** `tsc` 0 errores; vitest verde; los flujos commit/trigger SOLO
son alcanzables con acción explícita (checkbox/botón) — verificable por código: el
botón de commit está `disabled={!confirmChecked}`.
**Flag:** `STACKY_DEVOPS_PANEL_ENABLED` + degradación honesta según
`generator_enabled`/`trigger_enabled` del health.
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno adicional.

### F6 — Cierre: no-regresión total + verificación binaria de la serie

**Objetivo:** verificar que el plan quedó completo y nada existente se degradó.

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_flag.py tests/test_plan87_devops_endpoints.py tests/test_plan87_drafts_validation.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan73_generator_endpoint.py tests/test_plan73_repo_writer.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan72_ci_provider_trigger_port.py -q
.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest run src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Criterios binarios de done del plan (checklist):**
- [ ] Flag OFF ⇒ tab DevOps ausente, `/api/devops/parse-yaml` 404, cero cambio de
      comportamiento en flujos existentes (tests de no-regresión verdes).
- [ ] Flag ON + generator ON ⇒ crear 1 stage/1 job/1 step gráficamente y ver YAML ADO
      y GitLab en el preview (sin escribir YAML).
- [ ] Commit imposible sin checkbox de confirmación (HITL).
- [ ] Import de un `.gitlab-ci.yml` generado por el propio preview re-hidrata el editor
      (roundtrip F1 verde).
- [ ] `DEVOPS_SECTIONS` exportado y documentado para los planes 88/89 de la serie.
- [ ] Archivos de test registrados en ambos scripts de ratchet.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Drift entre tipos TS y `dict_to_spec` | Tipos espejo con nombres EXACTOS snake_case + test roundtrip F1 (YAML generado → parse → mismos campos) |
| `asdict` sobre dataclasses con tuplas anidadas | Cubierto por `test_f1_parse_yaml_roundtrip_gitlab` (falla temprano si la serialización no es JSON-safe) |
| Validación aditiva de drafts rompe PUT existente | Key ausente = no-op literal (mismo patrón plan 45) + `test_f2_absent_key_noop` |
| Meta-tests del arnés (default/curated, PlainHelp, wiring, ratchet) | F0 los corre explícitamente como no-regresión |
| Frontend sin test runner de componentes | Lógica en `specBuilder.ts` puro (vitest); componentes finos; gate tsc |
| Operador confundido si generator/trigger OFF | Health expone los 3 booleans y la UI degrada con mensajes que nombran la flag exacta |

## 6. Fuera de scope (v1)

- Drag & drop (v1 usa botones ↑/↓; DnD es azúcar, no valor).
- Commit a ADO (el backend ya devuelve 501 render-only, `pipeline_generator.py:86-88`;
  la UI lo comunica y deshabilita).
- Publicaciones de procesos batch/agenda/TODO ⇒ plan 2 de la serie.
- Inicialización de ambientes ⇒ plan 3 de la serie.
- Templates/galería de pipelines predefinidos.
- Edición simultánea de múltiples pipelines (1 spec activo por vez + borradores).

## 7. Glosario

- **PipelineSpec**: dataclass frozen pura que describe un pipeline (stages→jobs→steps)
  agnóstico del tracker; se renderiza a YAML ADO o GitLab (`services/pipeline_spec.py:55`).
- **Renderer**: función pura spec→YAML (`to_ado_yaml`/`to_gitlab_yaml`) o inversa
  YAML→spec (`parse_*_yaml`) en `services/pipeline_renderers.py`.
- **HITL** (human-in-the-loop): ninguna acción con efectos externos (commit, trigger)
  ocurre sin confirmación explícita del operador; riel innegociable de Stacky.
- **FLAG_REGISTRY / FlagSpec**: registro declarativo de flags del arnés
  (`services/harness_flags.py`), editable por UI en Configuración → Arnés.
- **client_profile**: JSON por proyecto editable por UI (GET/PUT en
  `api/client_profile.py`), usado para catálogo de procesos (plan 45) y ahora borradores.
- **Ratchet**: meta-test (plan 49 F4) que obliga a registrar todo archivo de test
  nuevo en `scripts/run_harness_tests.{sh,ps1}`.
- **Tracker**: sistema de tickets/repos (Azure DevOps o GitLab).
- **RepoWriter**: puerto que commitea archivos al repo del tracker
  (`services/repo_writer.py:30`); GitLab real, ADO 501 en v1.

## 8. Orden de implementación

1. F0 — flag + categoría + help (tests meta verdes).
2. F1 — blueprint `/api/devops` (health + parse-yaml) + centinela de ruta.
3. F2 — validación aditiva de `devops_pipeline_drafts`.
4. F3 — `specBuilder.ts` puro + namespaces en `endpoints.ts` (vitest verde).
5. F4 — `DevOpsPage` + wiring App.tsx (tab gated).
6. F5 — builder visual + preview + commit modal HITL + trigger/monitor.
7. F6 — cierre: no-regresión total + checklist binario.

## 9. Definición de Hecho (DoD)

- Todos los tests nombrados en F0-F2 verdes por archivo con el venv del repo.
- Vitest de `specBuilder.test.ts` verde; `npx tsc --noEmit` 0 errores.
- Tests de no-regresión (plan 73, 72, harness meta-tests) verdes.
- Con `STACKY_DEVOPS_PANEL_ENABLED=false` (default): comportamiento byte-idéntico.
- Checklist de F6 completo.
- Ningún contrato existente modificado (solo adiciones).
