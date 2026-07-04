# Plan 87 — Panel DevOps: creador GRÁFICO de pipelines

**Estado:** PROPUESTO
**Versión:** v1 → v2 (crítica adversarial `criticar-y-mejorar-plan`, 2026-07-04)
**Fecha:** 2026-07-03 (v1) / 2026-07-04 (v2)
**Serie DevOps:** plan 1 de 3 (base). Los planes siguientes de la serie (publicaciones
parametrizables de procesos batch/agenda/TODO, e inicialización de ambientes) se montan
SOBRE este panel sin refactor.
**Dependencias:** ninguna dentro de la serie (es la base); requiere planes 71/72/73 ya
implementados — VERIFICADO en código:

## CHANGELOG v1 → v2

- **C1 (BLOQUEANTE, resuelto):** el PUT de client_profile REEMPLAZA el profile completo
  (`save_client_profile(project_name, profile)`, `api/client_profile.py:161`; `previous`
  solo alimenta telemetría). La v1 dejaba el guardado de borradores como "usar los
  endpoints existentes" ⇒ un modelo menor habría PUTeado solo
  `{"devops_pipeline_drafts": [...]}` y BORRADO `process_catalog` y el resto de la
  config del operador. v2 fija contrato literal **GET → merge → PUT** con helper puro
  `mergeDraftsIntoProfile` testeado (F3) y flujo explícito en F5.
- **C2 (BLOQUEANTE, resuelto):** vitest NO está instalado en el frontend (no figura en
  `frontend/package.json`, no hay `vitest.config.*` ni binario en `node_modules/.bin`);
  el gate v1 "npx vitest run" era un falso gate (npx descargaría vitest ad-hoc, no
  determinista). v2 agrega paso F3.0: instalar `vitest` como devDependency (commiteando
  `package.json` + lockfile) y correr SIEMPRE por archivo para no colectar los `.tsx`
  huérfanos de `src/components/__tests__/` (importan `@testing-library/react`, que NO
  está instalada — gap preexistente que NO se toca).
- **C3 (IMPORTANTE, resuelto):** el snippet `FlagSpec` de F0 omitía `label` y `group`,
  que son campos REQUERIDOS del dataclass (`services/harness_flags.py:21-33`) ⇒
  TypeError al importar. v2 trae el snippet completo y literal.
- **C4 (IMPORTANTE, resuelto):** contrato de serie roto: el plan 88 F5 asume que las
  secciones reciben el health "por prop", pero la v1 definía
  `render: () => JSX.Element` (sin argumentos) ⇒ 88/89 habrían necesitado refactor del
  contenedor, exactamente lo que la serie promete evitar. v2 define
  `render: (ctx: DevOpsSectionContext) => ReactNode` desde el día 1.
- **C5 (IMPORTANTE, resuelto):** F3/F5 v1 decían "si ya existiera un namespace para /ci
  reusarlo" ⇒ inferencia. VERIFICADO: `CIPipeline.preview/trigger/monitor` YA existe
  (`frontend/src/api/endpoints.ts:2942-2969`). v2 lo referencia literal y prohíbe crear
  un namespace CI nuevo. Además el pseudo-helper `http("/devops/health")` no existe: el
  helper real es `api.get/api.post` con path `/api/...` (forma de `Migrator.health`,
  `endpoints.ts:3015`) — snippets corregidos.
- **C6 (IMPORTANTE, resuelto):** el payload del trigger CI quedaba en "leer antes de
  implementar". v2 inlinea el contrato verificado de `api/ci.py:76-131`:
  `POST /api/ci/<project>/trigger` con `{ref (obligatorio, normalize_ref → 400 si
  vacío), sha (opcional), item_id (opcional), confirm: true}`; respuesta puede ser
  `status:"reused"` (idempotencia 60s).
- **C7 (MENOR, resuelto):** la validación de drafts F2 no tenía cap ni unicidad de
  `name` ⇒ client_profile creciendo sin límite y selector ambiguo. v2: máx 50 drafts,
  `name` único y ≤120 chars (+3 tests).
- **C8 (MENOR, resuelto):** `test_f0_config_default_off` era frágil si la env var está
  seteada en el proceso del runner. v2 prescribe `monkeypatch.delenv` + reload del
  módulo config.
- **C9 (MENOR, resuelto):** `JSX.Element` en el registro de secciones → v2 usa
  `ReactNode` (evita depender del namespace global JSX según versión de @types/react).
- **[ADICIÓN ARQUITECTO]:** centinela anti-drift del contrato spec TS↔Python
  (`test_f1_spec_shape_frozen`): congela las keys de `asdict(dict_to_spec(...))` en los
  4 niveles contra listas literales espejo de las interfaces de `specBuilder.ts`. Si
  alguien agrega un campo a `PipelineSpec` sin actualizar los tipos TS (o viceversa),
  rompe con mensaje que apunta al archivo a actualizar. Protege a TODA la serie (88/89
  montan sobre el mismo contrato).

| Pieza existente | Evidencia (archivo:línea) |
|---|---|
| PipelineSpec/Step/Job/Stage + dict_to_spec + validate | `backend/services/pipeline_spec.py:27,36,48,55,63,69` |
| Renderers to_ado_yaml / to_gitlab_yaml / parse_ado_yaml / parse_gitlab_yaml | `backend/services/pipeline_renderers.py:23,126,194,251` |
| POST /api/pipeline-generator/preview (puro) | `backend/api/pipeline_generator.py:35` |
| POST /api/pipeline-generator/commit (HITL confirm=True, guard flag, spec en body ROOT) | `backend/api/pipeline_generator.py:53,59-60,61,56` |
| Commit ADO → 501 render-only | `backend/api/pipeline_generator.py:86-89` (NotImplementedError → 501) |
| RepoWriter factory | `backend/services/repo_writer.py:30` |
| Protocol CIProvider + factory get_ci_provider | `backend/services/ci_provider.py:83,107` |
| Adapters CI ADO/GitLab | `backend/services/ado_ci_provider.py:31`, `backend/services/gitlab_ci_provider.py:62` |
| Trigger/monitor HITL /api/ci/... | `backend/api/ci.py:26,76,139,174` |
| Namespace CI frontend YA existente (NO crear otro) | `frontend/src/api/endpoints.ts:2942` (`CIPipeline.preview/trigger/monitor`) |
| Patrón de página nueva gated por flag | `frontend/src/pages/MigratorPage.tsx:15`, `frontend/src/App.tsx:29,31,60,80-88,213-221,234` |
| Persistencia editable por UI en client_profile (PUT = REPLACE total) | `backend/api/client_profile.py:94,127,138-156,161` |

---

## 1. Objetivo + KPI

Crear la sección **DevOps** de Stacky: una página nueva de UI donde el operador arma
pipelines de forma **visual** (stages → jobs → steps como bloques con propiedades
editables), ve el **preview del YAML** resultante para ADO y GitLab en vivo, y — con
confirmación explícita — lo **commitea al repo** y lo **dispara/monitorea**. El editor
gráfico NO genera YAML por su cuenta: produce un dict `PipelineSpec` y reusa al 100%
los endpoints del plan 73 (`/preview`, `/commit`) y del plan 72 (`/api/ci/...`).

**KPI / impacto esperado** (aspiracional, NO es criterio de done — los criterios
binarios están en F6):
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
10. **NUNCA PUTear un client_profile parcial (C1):** `put_client_profile` REEMPLAZA el
    profile completo (`api/client_profile.py:161`). Todo guardado de borradores hace
    **GET del profile actual → merge en memoria → PUT del profile completo**. Prohibido
    enviar `{"devops_pipeline_drafts": [...]}` solo: borraría el resto de la config.

## 4. Fases

> Comando de tests backend (por archivo, con el venv del repo — la suite completa está
> contaminada, plan 49):
> `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/<archivo>" -q`
> ejecutado desde `Stacky Agents/backend` (o con `cd` previo; los tests asumen cwd=backend).
> Gate frontend: `npx tsc --noEmit` en `Stacky Agents/frontend` (0 errores) + vitest
> POR ARCHIVO tras F3.0 (ver C2: NUNCA `npx vitest run` sin archivo — colectaría los
> `.tsx` de `src/components/__tests__/` que importan `@testing-library/react`
> inexistente y daría rojo por un gap preexistente ajeno a este plan).

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
   - En `_CATEGORY_KEYS` (línea ~105) agregar la categoría NUEVA (después de
     `"migrador_ado_gitlab"`, línea ~167):
     ```python
     "devops": (
         "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 87 — panel DevOps: creador gráfico de pipelines
     ),
     ```
   - Agregar el `CategorySpec` de `devops` imitando byte a byte la ESTRUCTURA del de
     `migrador_ado_gitlab` (constructor posicional, línea ~94:
     `CategorySpec("migrador_ado_gitlab", "Migrador ADO → GitLab", ...)`; copiar todos
     los campos que tenga — `description`, `tier`, `intent`, etc. del plan 78 — con
     valores propios: id `"devops"`, label `"DevOps"`, descripción "Panel DevOps:
     creación gráfica de pipelines y operaciones de publicación", tier/intent = los
     mismos valores que use `migrador_ado_gitlab`).
   - Agregar el `FlagSpec` (cerca del de `STACKY_PIPELINE_GENERATOR_ENABLED`,
     línea ~1912). Snippet COMPLETO — `label` y `group` son campos REQUERIDOS del
     dataclass (`harness_flags.py:21-33`), no omitirlos (FIX C3):
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_PANEL_ENABLED",
         type="bool",
         label="Panel DevOps (Plan 87)",
         description=(
             "Plan 87 — Muestra la seccion DevOps en la UI (creador grafico de "
             "pipelines). Expone GET /api/devops/health y POST /api/devops/parse-yaml. "
             "Default OFF. Con OFF la tab no aparece y parse-yaml retorna 404."
         ),
         group="global",  # mismo group que STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED (harness_flags.py:1936)
         env_only=False,  # editable por UI (categoría 'devops')
         requires="STACKY_PIPELINE_GENERATOR_ENABLED",  # Plan 82 — el preview/commit viven detras de esa flag
     )
     ```
     ⚠️ SIN `default=` (gotcha `_CURATED_DEFAULTS_ON`). ⚠️ SIN `reserved=` (tiene
     consumidor real en F1).
3. `Stacky Agents/backend/services/harness_flags_help.py` — agregar la entrada
   `PlainHelp` para `STACKY_DEVOPS_PANEL_ENABLED` imitando la estructura de
   `STACKY_PIPELINE_GENERATOR_ENABLED` (línea 595): texto llano, qué pasa ON/OFF,
   ejemplo cotidiano.

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan87_devops_flag.py`:
- `test_f0_flag_in_registry`: `STACKY_DEVOPS_PANEL_ENABLED` está en `FLAG_REGISTRY`,
  `env_only is False`, `requires == "STACKY_PIPELINE_GENERATOR_ENABLED"`,
  `group == "global"`, `label` no vacío.
- `test_f0_flag_in_category_devops`: la key está en `_CATEGORY_KEYS["devops"]`.
- `test_f0_config_default_off` (FIX C8 — inmune al env del runner):
  ```python
  def test_f0_config_default_off(monkeypatch):
      monkeypatch.delenv("STACKY_DEVOPS_PANEL_ENABLED", raising=False)
      import importlib, config
      importlib.reload(config)
      assert config.config.STACKY_DEVOPS_PANEL_ENABLED is False
  ```
  (monkeypatch restaura el env al salir; si otros tests del archivo dependen de config,
  hacer `importlib.reload(config)` también en teardown — copiar el patrón si ya existe
  en algún test de flags del repo, si no, este snippet es autosuficiente).
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

### F1 — Backend: blueprint `/api/devops` (health + parse-yaml) + centinela de contrato

**Objetivo:** dar al frontend (a) un health para gatear la tab (patrón migrador),
(b) un endpoint PURO para importar YAML existente al editor gráfico, y (c) el
centinela anti-drift del contrato spec (ADICIÓN ARQUITECTO).

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
(Nota: si el YAML parsea a un no-dict — p.ej. un string suelto — `doc.get` en los
parsers levanta AttributeError; el `except Exception` de arriba lo convierte en 400.
Cubierto por `test_f1_parse_yaml_bad_input_400`.)

**Registro:** en `Stacky Agents/backend/api/__init__.py`, imitar EXACTAMENTE las dos
líneas del plan 73 (import y `api_bp.register_blueprint`):
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
- `test_f1_parse_yaml_roundtrip_ado`: ídem con `to_ado_yaml` y `source="ado"` (cubre
  `parse_ado_yaml`, que el roundtrip gitlab no toca).
- `test_f1_parse_yaml_bad_input_400`: flag ON; body sin `yaml` → 400; `source="foo"` → 400;
  yaml malformado (`"::::not yaml"`) → 400 (nunca 500).
- `test_f1_route_registered`: centinela — `create_app()` y assert que
  `"/api/devops/health"` está en `[r.rule for r in app.url_map.iter_rules()]`
  (patrón centinela del plan 74).
- **[ADICIÓN ARQUITECTO]** `test_f1_spec_shape_frozen` — centinela anti-drift del
  contrato TS↔Python. Congela las keys de la serialización que consume el frontend:
  ```python
  def test_f1_spec_shape_frozen():
      """Si este test rompe, actualizar frontend/src/devops/specBuilder.ts (tipos espejo)
      Y estas listas, en el MISMO commit. Protege a los planes 88/89 de la serie."""
      from dataclasses import asdict
      from services.pipeline_spec import dict_to_spec
      spec = asdict(dict_to_spec({
          "name": "p", "stages": [{"name": "s", "jobs": [
              {"name": "j", "steps": [{"name": "st", "script": "echo"}]}
          ]}],
      }))
      assert sorted(spec.keys()) == ["name", "raw_yaml", "raw_yaml_target", "stages", "trigger_branches", "variables"]
      assert sorted(spec["stages"][0].keys()) == ["condition", "jobs", "name"]
      assert sorted(spec["stages"][0]["jobs"][0].keys()) == ["artifacts", "image", "name", "pool_vm_image", "runner_tags", "services", "steps", "variables"]
      assert sorted(spec["stages"][0]["jobs"][0]["steps"][0].keys()) == ["condition", "env", "name", "script", "working_directory"]
  ```
  (Listas verificadas contra `services/pipeline_spec.py:27-61`.)

**Registro ratchet:** agregar el archivo a ambos scripts de ratchet.

**Criterio binario:** 8 tests verdes; `test_plan73_generator_endpoint.py` sigue verde
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
Límites (FIX C7): máximo **50** drafts; `name` obligatorio, **único** dentro de la
lista y de **≤120** caracteres.

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
    if len(drafts) > 50:
        return jsonify({"ok": False, "error": "devops_pipeline_drafts: maximo 50 borradores."}), 400
    seen_names = set()
    for idx, d in enumerate(drafts):
        if not isinstance(d, dict) or not isinstance(d.get("name"), str) or not d.get("name").strip():
            return jsonify({"ok": False, "error": f"devops_pipeline_drafts[{idx}].name es obligatorio (string no vacio)."}), 400
        name = d["name"].strip()
        if len(name) > 120:
            return jsonify({"ok": False, "error": f"devops_pipeline_drafts[{idx}].name supera 120 caracteres."}), 400
        if name in seen_names:
            return jsonify({"ok": False, "error": f"devops_pipeline_drafts[{idx}].name duplicado: '{name}'."}), 400
        seen_names.add(name)
        if not isinstance(d.get("spec"), dict):
            return jsonify({"ok": False, "error": f"devops_pipeline_drafts[{idx}].spec debe ser un objeto."}), 400
```
NO validar el spec contra `_validate_spec` acá: un borrador PUEDE estar incompleto
(mismo criterio que "kind vacío se tolera (borrador en edición)" del plan 45,
`client_profile.py:148`). La validación dura ocurre en `/preview`//`/commit`.

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan87_drafts_validation.py`:
- `test_f2_absent_key_noop`: PUT de un profile SIN la key → mismo resultado que hoy
  (200/`ok:true` con un profile mínimo válido; copiar el setup del test de PUT exitoso
  más simple de `tests/test_client_profile_endpoints.py`).
- `test_f2_drafts_not_list_400`: `"devops_pipeline_drafts": {}` → 400.
- `test_f2_draft_without_name_400`: `[{"spec": {}}]` → 400.
- `test_f2_draft_without_spec_400`: `[{"name": "x"}]` → 400.
- `test_f2_over_50_drafts_400` (FIX C7): 51 drafts válidos → 400.
- `test_f2_duplicate_name_400` (FIX C7): 2 drafts con `name="a"` → 400.
- `test_f2_name_over_120_chars_400` (FIX C7): name de 121 chars → 400.
- `test_f2_valid_drafts_persist`: PUT con 1 draft válido → 200; GET
  (`get_client_profile`, `client_profile.py:94`) devuelve la key intacta.
- `test_f2_incomplete_spec_tolerated`: draft con `spec = {"name": "", "stages": []}`
  (inválido para publicar) → 200 (borrador en edición se tolera).

**Registro ratchet:** agregar el archivo a ambos scripts.

**Criterio binario:** 9 tests verdes; `tests/test_client_profile_endpoints.py` sigue
verde (no-regresión).
**Flag:** ninguna (validación aditiva inerte: con flag OFF nadie envía la key ⇒
byte-idéntico).
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Frontend: vitest + modelo puro del builder (`specBuilder.ts`) + API client

**Objetivo:** toda la lógica de edición del pipeline como funciones puras testeables
con vitest (TS puro, sin React), y los namespaces de API.

**F3.0 — Instalar vitest (FIX C2, prerequisito del gate):**
vitest NO está instalado hoy (`frontend/package.json` no lo tiene; no hay
`vitest.config.*` ni binario en `node_modules/.bin`). Ejecutar en
`Stacky Agents/frontend`:
```
npm install -D vitest
```
y commitear `package.json` + `package-lock.json`. Verificación binaria:
`npx vitest --version` responde sin descargar nada. NO instalar
`@testing-library/react` (fuera de scope; los `.tsx` de `src/components/__tests__/`
siguen huérfanos como hasta ahora). Por eso el comando de test es SIEMPRE por archivo
(nunca `npx vitest run` a secas).

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/specBuilder.ts`
- Tipos espejo EXACTOS del contrato de `dict_to_spec` (`pipeline_spec.py:69-107` —
  usar los MISMOS nombres de campo, snake_case incluido; el centinela
  `test_f1_spec_shape_frozen` congela estas keys del lado backend):
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
  para que el JSON matchee lo que `dict_to_spec` espera);
  `fromParsedSpec(dict): PipelineSpecDraft` (normaliza la respuesta `{spec}` de
  `/api/devops/parse-yaml`: las tuplas ya llegan como arrays por JSON; nulls
  preservados).
  Índices fuera de rango: devolver el spec SIN cambios (nunca throw).
- **`mergeDraftsIntoProfile(profile: object | null, drafts: object[]): object`
  (FIX C1):** función pura que devuelve `{...(profile ?? {}), devops_pipeline_drafts: drafts}`
  — copia superficial nueva, NO muta el input, preserva TODAS las keys ajenas
  (`process_catalog`, etc.). Es la ÚNICA vía por la que F5 construye el body del PUT.
- Defaults al agregar: `addStage` crea `{name: "stage-" + (n+1), jobs: []}`;
  `addJob` crea `{name: "job-1", steps: [], runner_tags: [], variables: {}, artifacts: [], services: []}`;
  `addStep` crea `{name: "step-1", script: "", env: {}}`.

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` — el helper real
es `api.get`/`api.post` con path completo `/api/...` (forma de `Migrator.health`,
línea 3015 — FIX C5). Agregar:
```ts
export const DevOps = {
  health: () =>
    api.get<{ flag_enabled: boolean; generator_enabled: boolean; trigger_enabled: boolean }>("/api/devops/health"),
  parseYaml: (source: "ado" | "gitlab", yaml: string) =>
    api.post<{ spec: object }>("/api/devops/parse-yaml", { source, yaml }),
};
export const PipelineGenerator = {
  /** 200 → {ado, gitlab}; 400 → {errors: [{field, message}]} (api/pipeline_generator.py:43). */
  preview: (spec: object) => api.post<{ ado: string; gitlab: string }>("/api/pipeline-generator/preview", spec),
  /** El spec va en el body ROOT junto a confirm/target/branch/project (api/pipeline_generator.py:57-66). */
  commit: (body: object) => api.post<object>("/api/pipeline-generator/commit", body),
};
```
**NO crear un namespace CI nuevo (FIX C5):** `CIPipeline.preview/trigger/monitor` YA
existe en `endpoints.ts:2942-2969` con los payloads correctos; F5 lo importa tal cual.

**Tests PRIMERO** — archivo nuevo `Stacky Agents/frontend/src/devops/specBuilder.test.ts`
(vitest TS puro, sin imports de React ni de endpoints.ts):
- `emptySpec_shape`: emptySpec() tiene stages=[], variables={}, trigger_branches=[].
- `addStage_appends_and_is_immutable`: el spec original NO cambia (`!==` y deep-equal
  al snapshot previo).
- `move_out_of_range_noop`: moveStage(spec, 0, -1) con 1 stage → igual.
- `remove_indices_out_of_range_noop`.
- `nested_add_update`: addStage→addJob→addStep→updateStep(script:"make build") deja el
  script en su lugar y solo ahí.
- `toSpecDict_omits_nullish`: un StepDraft sin condition ⇒ el dict NO tiene la key
  `condition`.
- `import_hydrates_from_parse_result`: `fromParsedSpec` con el fixture literal del
  roundtrip de F1 (la respuesta `{spec}` de parse-yaml) produce un
  `PipelineSpecDraft` editable con los mismos campos.
- `mergeDrafts_preserves_foreign_keys` (FIX C1): dado
  `profile = {process_catalog: [{kind: "batch"}], otra_key: 1}`,
  `mergeDraftsIntoProfile(profile, [d])` devuelve un objeto NUEVO con
  `process_catalog` y `otra_key` INTACTOS + `devops_pipeline_drafts=[d]`, y el input
  no mutó.
- `mergeDrafts_null_profile`: `mergeDraftsIntoProfile(null, [])` →
  `{devops_pipeline_drafts: []}` (caso proyecto sin client_profile).
Comando: `npx vitest run src/devops/specBuilder.test.ts` en `Stacky Agents/frontend`.

**Criterio binario:** `npx vitest --version` funciona sin descarga; vitest verde
(9 tests) + `npx tsc --noEmit` 0 errores.
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
  (`useQuery` de `@tanstack/react-query`, mismo import que `MigratorPage.tsx:8`).
- Registro extensible (EXPORTADO para los planes 2/3). Contrato v2 (FIX C4/C9): las
  secciones RECIBEN el contexto del panel — el plan 88 asume el health por prop
  (88 §F5) y así no hay refactor del contenedor jamás:
  ```ts
  export interface DevOpsHealth { flag_enabled: boolean; generator_enabled: boolean; trigger_enabled: boolean; }
  export interface DevOpsSectionContext { health: DevOpsHealth; refetchHealth: () => void; }
  export interface DevOpsSection { id: string; label: string; render: (ctx: DevOpsSectionContext) => ReactNode; }
  export const DEVOPS_SECTIONS: DevOpsSection[] = [
    { id: "pipelines", label: "Pipelines", render: (ctx) => <PipelineBuilderSection ctx={ctx} /> },
    // Plan 88 (publicaciones) y Plan 89 (ambientes) agregan entradas ACA, sin refactor.
    // Las keys nuevas del health (p.ej. publications_enabled, plan 88 F3) viajan por
    // ctx.health de forma aditiva (ampliar DevOpsHealth con keys opcionales).
  ];
  ```
  (`ReactNode` importado de `react`; NO usar `JSX.Element` — FIX C9.)
- Sub-tabs internas simples (useState con el id activo; botones por sección);
  DevOpsPage construye `ctx` desde `healthQuery` (`refetchHealth = () => healthQuery.refetch()`).

**Archivo a editar:** `Stacky Agents/frontend/src/App.tsx` — replicar EXACTAMENTE el
patrón migrador en sus 5 puntos:
1. import `DevOpsPage` (junto al import de `MigratorPage`);
2. estado `const [devopsEnabled, setDevopsEnabled] = useState(false);` (junto a :60);
3. en el `useEffect` de :80-88, fetch `/api/devops/health` →
   `setDevopsEnabled(d.flag_enabled === true)` con `.catch(() => setDevopsEnabled(false))`;
4. redirect si tab activa sin flag (junto a :128):
   `else if (tab === "devops" && !devopsEnabled) selectTab("team");`
5. botón de nav condicional (junto a :213-221) + render
   `{tab === "devops" && devopsEnabled && <DevOpsPage />}` (junto a :234).
Además: agregar `"devops"` al union `type Tab` (`App.tsx:29`) y la entrada
`devops: "/devops"` a `TAB_PATHS` (`App.tsx:31`), mismo formato que `migrador`.

**Tests:** no hay test runner de componentes (sin `@testing-library/react`).
Gate = `npx tsc --noEmit` 0 errores + verificación manual binaria del criterio.

**Criterio binario:** (a) `tsc` 0 errores; (b) con flag OFF el fetch devuelve
`flag_enabled:false` ⇒ la tab NO se renderiza (verificable en el código: el botón está
dentro de `{devopsEnabled && ...}`); (c) `DEVOPS_SECTIONS` exportado con 1 entrada y
firma `render(ctx)`.
**Flag:** `STACKY_DEVOPS_PANEL_ENABLED` (gatea tab y página).
**Runtimes:** sin impacto.
**Trabajo del operador:** opt-in — activar la flag desde Configuración → Arnés
(HarnessFlagsPanel, categoría "devops"); ningún otro paso.

### F5 — Frontend: PipelineBuilder (bloques + propiedades + preview + import)

**Objetivo:** el editor visual propiamente dicho, 100% sobre `specBuilder.ts` (F3) y
los endpoints existentes.

**Archivos NUEVOS** (en `Stacky Agents/frontend/src/components/devops/`):
1. `PipelineBuilderSection.tsx` — recibe `ctx: DevOpsSectionContext` (F4); orquesta:
   estado `spec: PipelineSpecDraft` (useState, inicial `emptySpec()`), layout 2
   columnas: izquierda árbol de bloques, derecha panel de propiedades + preview.
   Barra superior: nombre del pipeline, selector de borrador, botón "Importar YAML"
   (textarea + selector ado/gitlab → `DevOps.parseYaml` → `fromParsedSpec` → hidrata
   `spec`), botones "Preview" / "Commit al repo…" / "Disparar…".
   **Flujo de borradores (FIX C1 — read-modify-write OBLIGATORIO, riel §3.10):**
   - Cargar: `GET /api/projects/<name>/client-profile` (ruta del decorador
     `client_profile.py:93`) → `drafts = json.profile?.devops_pipeline_drafts ?? []`.
   - Guardar: (1) GET fresco del profile; (2) `base = json.profile ?? {}`;
     (3) `merged = mergeDraftsIntoProfile(base, nuevosDrafts)` (helper puro de F3);
     (4) `PUT /api/projects/<name>/client-profile` con body `{ profile: merged }`
     (el endpoint acepta `{profile: ...}` o el objeto directo, `client_profile.py:132`;
     usar el wrapper explícito). PROHIBIDO PUTear solo la key de drafts: el PUT
     REEMPLAZA el profile completo (`client_profile.py:161`) y borraría
     `process_catalog` y el resto.
   - Si el PUT devuelve 400 (validación F2), mostrar el `error` literal del backend.
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
   `field: message` en rojo (contrato exacto: `api/pipeline_generator.py:43`); si
   `ctx.health.generator_enabled === false`, mostrar aviso "Activá
   STACKY_PIPELINE_GENERATOR_ENABLED (categoría épicas/ADO) para preview/commit" en
   lugar de llamar (el endpoint daría 404, `pipeline_generator.py:37`).
5. `CommitPipelineModal.tsx` — HITL: selector target (`gitlab`; opción `ado`
   deshabilitada con nota "ADO: render-only v1 — commit devuelve 501",
   `pipeline_generator.py:86-89`), input branch (placeholder
   `feature/pipeline-<slug>`, default vacío ⇒ backend deriva,
   `pipeline_generator.py:71`), input project (default: proyecto activo de
   `useWorkbench`, patrón `MigratorPage.tsx:16-17`), checkbox OBLIGATORIO
   "Confirmo el commit de este pipeline al repositorio" que habilita el botón; submit
   ⇒ `PipelineGenerator.commit({...toSpecDict(spec), target, branch, project, confirm: true})`
   (el spec va en el body ROOT: `commit_route` hace `dict_to_spec(body)`,
   `pipeline_generator.py:61`); mostrar resultado (éxito con datos del commit / error
   con `error` y `kind`). Al éxito, recordar el `branch` usado (estado local) para
   ofrecerlo como `ref` default en el trigger (FIX C6).
6. `TriggerPipelineSection.tsx` — SOLO si `ctx.health.trigger_enabled === true`.
   REUSA `CIPipeline` de `endpoints.ts:2942` (FIX C5; NO crear namespace nuevo).
   Contrato verificado de `api/ci.py:76-131` (FIX C6):
   - Input `ref` (obligatorio; default = branch del último commit exitoso del modal,
     si no, vacío y el operador lo escribe; el backend responde 400 si es vacío/inválido
     vía `normalize_ref`).
   - Paso 1 (HITL informado): `CIPipeline.preview(project, ref)` → GET
     `/api/ci/<project>/trigger-preview` (`ci.py:139`); mostrar ref resuelto +
     `would_reuse`.
   - Paso 2 (acción explícita): botón "Disparar" →
     `CIPipeline.trigger(project, ref, "", "", true)` (sha y item_id vacíos: este
     flujo no está atado a un work item; `ci.py:115-119` los tolera). Si la respuesta
     trae `status: "reused"`, mostrar "pipeline reciente reusado (idempotencia 60s)".
   - Polling de estado: `CIPipeline.monitor(project, pipelineId)` (`ci.py:174`).
   Si `trigger_enabled:false` ⇒ sección oculta con nota que nombra la flag
   `STACKY_PIPELINE_TRIGGER_ENABLED`.

**Tests:** lógica ya cubierta en F3 (vitest puro, incluye `fromParsedSpec` y
`mergeDraftsIntoProfile`). Componentes: gate `tsc`.

**Criterio binario:** `tsc` 0 errores; vitest F3 sigue verde; los flujos commit/trigger
SOLO son alcanzables con acción explícita (checkbox/botón) — verificable por código: el
botón de commit está `disabled={!confirmChecked}`; el guardado de borradores pasa por
`mergeDraftsIntoProfile` (grep: ninguna llamada a PUT client-profile fuera de ese flujo).
**Flag:** `STACKY_DEVOPS_PANEL_ENABLED` + degradación honesta según
`generator_enabled`/`trigger_enabled` del health (vía `ctx`).
**Runtimes:** sin impacto.
**Trabajo del operador:** ninguno adicional.

### F6 — Cierre: no-regresión total + verificación binaria de la serie

**Objetivo:** verificar que el plan quedó completo y nada existente se degradó.

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_flag.py tests/test_plan87_devops_endpoints.py tests/test_plan87_drafts_validation.py -q
.venv/Scripts/python.exe -m pytest tests/test_client_profile_endpoints.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan73_generator_endpoint.py tests/test_plan73_repo_writer.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan72_ci_provider_trigger_port.py -q
.venv/Scripts/python.exe -m pytest tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest --version
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
- [ ] Guardar un borrador NO pierde ninguna key ajena del client_profile
      (`mergeDrafts_preserves_foreign_keys` verde + flujo F5.1 read-modify-write).
- [ ] `test_f1_spec_shape_frozen` verde (contrato TS↔Python congelado para 88/89).
- [ ] `DEVOPS_SECTIONS` exportado con firma `render(ctx)` y documentado para los
      planes 88/89 de la serie.
- [ ] vitest instalado como devDependency (package.json + lockfile commiteados);
      `npx vitest run src/devops/specBuilder.test.ts` verde.
- [ ] Archivos de test registrados en ambos scripts de ratchet.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **PUT de client_profile REEMPLAZA el profile ⇒ guardar drafts podría borrar config del operador (C1)** | Riel §3.10 + flujo F5 read-modify-write literal + helper puro `mergeDraftsIntoProfile` + tests `mergeDrafts_*` |
| **vitest inexistente ⇒ gate falso-verde (C2)** | F3.0 lo instala como devDependency con verificación binaria (`npx vitest --version`); corrida SIEMPRE por archivo para no colectar los `.tsx` huérfanos preexistentes |
| Drift entre tipos TS y `dict_to_spec` | Tipos espejo con nombres EXACTOS snake_case + roundtrips F1 (gitlab Y ado) + centinela `test_f1_spec_shape_frozen` (ADICIÓN) |
| `asdict` sobre dataclasses con tuplas anidadas | Cubierto por los roundtrips F1 (falla temprano si la serialización no es JSON-safe) |
| Validación aditiva de drafts rompe PUT existente | Key ausente = no-op literal (mismo patrón plan 45) + `test_f2_absent_key_noop` + no-regresión `test_client_profile_endpoints.py` |
| client_profile inflado por drafts sin límite | Cap 50 + name único ≤120 chars (FIX C7) |
| Meta-tests del arnés (default/curated, PlainHelp, wiring, ratchet) | F0 los corre explícitamente como no-regresión; snippet FlagSpec completo con label/group (FIX C3) |
| Frontend sin test runner de componentes | Lógica en `specBuilder.ts` puro (vitest); componentes finos; gate tsc |
| Operador confundido si generator/trigger OFF | Health expone los 3 booleans y la UI degrada con mensajes que nombran la flag exacta (vía `ctx.health`) |
| Contrato de secciones insuficiente para 88/89 | `render(ctx: DevOpsSectionContext)` desde el día 1 (FIX C4); health se amplía con keys opcionales aditivas |

## 6. Fuera de scope (v1)

- Drag & drop (v1 usa botones ↑/↓; DnD es azúcar, no valor).
- Commit a ADO (el backend ya devuelve 501 render-only, `pipeline_generator.py:86-89`;
  la UI lo comunica y deshabilita).
- Publicaciones de procesos batch/agenda/TODO ⇒ plan 2 de la serie.
- Inicialización de ambientes ⇒ plan 3 de la serie.
- Templates/galería de pipelines predefinidos.
- Edición simultánea de múltiples pipelines (1 spec activo por vez + borradores).
- Instalar `@testing-library/react` / tests de componentes React (gap preexistente,
  no se amplía ni se cierra acá).

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
  `api/client_profile.py`), usado para catálogo de procesos (plan 45) y ahora
  borradores. OJO: el PUT reemplaza el documento COMPLETO (§3.10).
- **DevOpsSectionContext**: contrato v2 del registro de secciones — cada sección
  recibe `{health, refetchHealth}`; punto de extensión de los planes 88/89.
- **Ratchet**: meta-test (plan 49 F4) que obliga a registrar todo archivo de test
  nuevo en `scripts/run_harness_tests.{sh,ps1}`.
- **Tracker**: sistema de tickets/repos (Azure DevOps o GitLab).
- **RepoWriter**: puerto que commitea archivos al repo del tracker
  (`services/repo_writer.py:30`); GitLab real, ADO 501 en v1.

## 8. Orden de implementación

1. F0 — flag + categoría + help (tests meta verdes).
2. F1 — blueprint `/api/devops` (health + parse-yaml) + centinelas (ruta y spec-shape).
3. F2 — validación aditiva de `devops_pipeline_drafts` (con límites C7).
4. F3 — F3.0 vitest + `specBuilder.ts` puro (incl. `mergeDraftsIntoProfile`,
   `fromParsedSpec`) + namespaces en `endpoints.ts` (vitest verde).
5. F4 — `DevOpsPage` + `DevOpsSectionContext` + wiring App.tsx (tab gated).
6. F5 — builder visual + preview + commit modal HITL + trigger/monitor (reusando
   `CIPipeline`).
7. F6 — cierre: no-regresión total + checklist binario.

## 9. Definición de Hecho (DoD)

- Todos los tests nombrados en F0-F2 verdes por archivo con el venv del repo
  (4 + 8 + 9 = 21 tests backend).
- vitest instalado (F3.0) y `specBuilder.test.ts` verde (9 tests); `npx tsc --noEmit`
  0 errores.
- Tests de no-regresión (plan 73, 72, client_profile, harness meta-tests) verdes.
- Con `STACKY_DEVOPS_PANEL_ENABLED=false` (default): comportamiento byte-idéntico.
- Checklist de F6 completo (incluye: drafts sin pérdida de keys ajenas, spec-shape
  congelado, `render(ctx)`).
- Ningún contrato existente modificado (solo adiciones).
