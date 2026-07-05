# Plan 94 — Caja fuerte de variables: secretos del pipeline fuera del YAML (ADO + GitLab)

**Estado:** PROPUESTO
**Versión:** v1
**Fecha:** 2026-07-05
**Serie DevOps E2E:** plan 2 de 4 (93 preflight / 94 variables / 95 producción / 96 doctor).
**Requisito textual del operador (riel #1):** compatible con **Azure DevOps Y GitLab
desde el día 1**. Cada capacidad tiene pata en ambos trackers o degrada ámbar honesta.
**Dependencias:** plan 87 IMPLEMENTADO (`84a9ecb5`, panel host). Integraciones
ADITIVAS/OPCIONALES: plan 93 (el preflight consume `list_variables` si esta flag
está ON — ver 93 F3), plan 95 (la definición ADO que este plan necesita se crea con
"Llevar a producción"; sin ella, la pata ADO degrada honesta), plan 91 (bridge de
credenciales: SOLO nota de compatibilidad §6). Verificado en working tree 2026-07-05:

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| Blueprint del panel + health aditivo | `backend/api/devops.py:22,25-38` |
| Contrato §3.12: `DEVOPS_SECTIONS` declarativo + gate del shell | `frontend/src/pages/DevOpsPage.tsx:44,68` |
| `FlagGateBanner` | `frontend/src/components/devops/FlagGateBanner.tsx` |
| Builder 87: `spec.variables` editable (Pipeline properties) | `frontend/src/components/devops/BlockProperties.tsx`, `frontend/src/devops/specBuilder.ts` |
| Variables van HOY en texto plano al YAML commiteado | `backend/services/pipeline_renderers.py:47-49` (ado), `:148-149,163-164` (gitlab) |
| Cliente REST ADO con PAT | `backend/services/ado_client.py:257` (`_request`) |
| Cliente REST GitLab | `backend/services/gitlab_provider.py` (delegate `_request`) |
| Fábrica por tracker_type (patrón) | `backend/services/ci_provider.py:107` |
| Riel "secreto JAMÁS en JSON/logs/GET" (write-only + has_value) | plan 91 §3.1, `backend/services/server_registry.py`, `backend/api/devops_servers.py` |
| Guard anti-CSRF `request.is_json` en mutantes | plan 91 C5, `backend/api/devops_servers.py` (`_guard`) |
| Helper de definiciones ADO (compartido 93/95) | `backend/services/ado_pipeline_definitions.py` (lo crea el primero de 93/94/95 implementado; contenido EXACTO en 93 F2) |
| Patrón flag 5 patas + gotchas | `backend/config.py:857-859`, `harness_flags.py:177-183`, ratchet `run_harness_tests.ps1:103-125` |

---

## 1. Objetivo + KPI

Que el operador gestione **variables del pipeline por proyecto** desde una sección
nueva "Variables" del panel DevOps, marcando cada una como **secreta** (candado):

- Las **secretas** se crean EN EL TRACKER vía API — GitLab: project CI/CD variable
  con `masked`; ADO: variable de la pipeline definition con `isSecret:true` — y
  **JAMÁS tocan el YAML, el repo, el client_profile ni los logs** (riel §3.1 del 91).
- Las **normales** pueden seguir viviendo en `spec.variables` (comportamiento 87
  intacto) o crearse también en el tracker.
- En el builder del 87, una heurística detecta keys que "parecen secreto"
  (PASSWORD/TOKEN/etc.) en `spec.variables` y ofrece **"Mover a variable segura"**
  (1 click + confirmación): crea la variable en el tracker y la saca del spec.

**KPI (aspiracional; criterios binarios en F5):**
- 0 secretos commiteados al repo por el flujo DevOps (heurística + botón mover).
- Alta de una variable segura = 1 formulario + 1 confirmación, en ADO y en GitLab.
- El valor de un secreto es write-only: no aparece en NINGUNA respuesta GET ni log
  (test centinela, patrón KPI-2 del plan 91).

## 2. Por qué ahora / gap que cierra

Un pipeline real despliega contra servidores/servicios: necesita credenciales.
Hoy el único lugar para "variables" del flujo DevOps es `spec.variables`, que se
renderiza EN TEXTO PLANO dentro del YAML commiteado (`pipeline_renderers.py:47-49,
148-149`). El camino natural de un operador no-experto — poner la password ahí —
termina con el secreto versionado en el repo. Los trackers ya tienen el mecanismo
correcto (variables masked/secret inyectadas en runtime); solo falta el puente por
UI con el riel write-only que el plan 91 ya probó para el Credential Manager.

## 3. Principios y guardarraíles (NO negociables)

1. **PARIDAD ADO + GITLAB:** sub-puerto `CIVariablesProvider` con DOS adapters y
   fábrica por tracker_type. GitLab = project CI/CD variables API. ADO = variables
   de la pipeline definition (`isSecret`) — disponibles como `$(VAR)` en el YAML
   sin declararlas, igual que las de GitLab como `$VAR`. Si ADO no tiene definición
   aún ⇒ la sección degrada ámbar con CTA al plan 95 (nunca finge éxito).
2. **Secreto JAMÁS en disco/JSON/DB/logs/GET (riel 91 §3.1):** el valor entra SOLO
   por POST (write-only); GET devuelve `{key, is_secret, has_value}`; prohibido
   loggear el body de requests/responses de este plan; las excepciones HTTP que
   puedan contener el valor NUNCA propagan crudas (patrón 91 C1).
3. **HITL:** crear/actualizar/borrar una variable exige `confirm:true` en el body
   (server-side) + click explícito. Nada se sincroniza ni borra solo.
4. **Flag propia** `STACKY_DEVOPS_VARIABLES_ENABLED`: categoría `devops`,
   `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, SIN `default=`,
   CON `label`/`group`, `PlainHelp`, línea en `harness_defaults.env` + test.
   Default OFF; byte-idéntico con OFF (endpoints 404, sección con `FlagGateBanner`
   del shell).
5. **No degradar:** `PipelineSpec`/renderers INTACTOS (cero campos nuevos, cero
   cambios de YAML); el flujo 87 sin la flag es byte-idéntico. `CI_PORT_METHODS`
   intacto (sub-puerto nuevo).
6. **Guard anti-CSRF (91 C5):** métodos mutantes exigen `request.is_json` ⇒ 400.
7. **3 runtimes:** UI + Flask; impacto NINGUNO (declarado por fase).
8. **Mono-operador sin auth; cero trabajo extra** (opt-in); **ratchet** en ambos
   scripts.
9. **NUNCA PUTear client_profile parcial:** este plan NO persiste nada en
   client_profile (la fuente de verdad de variables es EL TRACKER — cero estado
   duplicado en Stacky).

## 4. Modelo de datos (contrato)

No hay persistencia nueva en Stacky. Contratos del sub-puerto (F2):

```python
list_variables() -> list[dict]   # [{"key": str, "is_secret": bool, "has_value": True,
                                 #   "masked": bool|None}]  — NUNCA "value"
set_variable(key: str, value: str, secret: bool) -> dict   # {"key", "is_secret", "masked": bool|None}
delete_variable(key: str) -> bool                          # False si no existía
```

Reglas de key (PURAS, F1): `^[A-Za-z_][A-Za-z0-9_]*$`, 1..255 chars (constraint
GitLab; ADO lo tolera). Heurística `looks_secret(key)`: regex case-insensitive
`(PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|PRIVATE|CRED|CONN(ECTION)?_?STR)`.

**Nota GitLab masked:** GitLab rechaza `masked:true` si el VALOR no cumple sus
reglas (≥8 chars, base64-like, sin saltos de línea). El adapter intenta
`masked:true`; si el tracker devuelve 400 por masking, reintenta `masked:false` y
devuelve `masked:false` — la UI muestra "guardada como secreta pero NO enmascarable
en logs de GitLab (el valor no cumple las reglas de masking)". Honestidad, no magia.

## 5. Fases

> Comandos de test: backend `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> desde `Stacky Agents/backend`; frontend `npx tsc --noEmit` + `npx vitest run
> <archivo>` (vitest ya instalado, correr por archivo).

### F0 — Flag `STACKY_DEVOPS_VARIABLES_ENABLED` (5 patas)

Misma mecánica EXACTA que 93 F0 (espejo de `test_plan91_servers_flag.py`),
cambiando la key. `FlagSpec` con `label="Variables del pipeline (Plan 94)"` y
description en llano: "Caja fuerte de variables: las secretas se guardan en el
tracker (GitLab masked / ADO isSecret), nunca en el YAML ni en archivos de Stacky.
Default OFF: /api/devops/variables da 404 y la sección no aparece."

**Tests PRIMERO** — `tests/test_plan94_variables_flag.py`: los mismos 5 casos del
patrón (registry/categoría/default off/plain help/harness_defaults) + no-regresión
`test_harness_flags.py` y `test_flag_wiring.py` (misma nota del plan 85: F0+F3 en
el mismo commit si el wiring acusa).
**Ratchet:** registrar. **Criterio binario:** 5+2 verdes; default OFF.
**Flag:** `STACKY_DEVOPS_VARIABLES_ENABLED`. **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F1 — Helpers PUROS (`validate_variable_key` / `looks_secret`)

**Objetivo:** validación y heurística deterministas, compartidas backend/frontend
por paridad de datos.

**Archivo NUEVO:** `Stacky Agents/backend/services/ci_variables.py` (el Protocol
va en F2; acá nacen los helpers puros del mismo módulo):
```python
"""ci_variables.py — Plan 94. Sub-puerto de variables CI + helpers PUROS.
Los helpers no hacen I/O. El VALOR de un secreto jamás se loggea ni retorna."""
import re

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_HINT_RE = re.compile(
    r"(PASSWORD|PASSWD|PWD|SECRET|TOKEN|APIKEY|API_KEY|PRIVATE|CRED|CONN(ECTION)?_?STR)",
    re.IGNORECASE,
)

def validate_variable_key(key: str) -> str | None:
    """None si OK; mensaje en llano si no (vacía, regex, >255)."""

def looks_secret(key: str) -> bool:
    """True si el NOMBRE sugiere secreto (heurística, solo por key, nunca por valor)."""
```

**Archivo NUEVO (fixture compartido py↔ts, patrón 88):**
`Stacky Agents/backend/tests/fixtures/plan94_secret_hints.json` — contenido literal:
```json
{
  "secret": ["DB_PASSWORD", "password", "GITLAB_TOKEN", "ApiKey", "MY_API_KEY",
              "SSH_PRIVATE_KEY", "CONN_STR", "ConnectionString", "SVC_CRED"],
  "not_secret": ["DEPLOY_PATH", "ENVIRONMENT", "TIMEOUT_SECONDS", "TARGET_HOST",
                 "KEYBOARD_LAYOUT", "MONKEY"]
}
```
(Nota: `KEYBOARD`/`MONKEY` NO deben matchear — el regex exige los tokens listados,
no la substring `KEY` suelta: por eso `APIKEY|API_KEY` y no `KEY`.)

**Tests PRIMERO** — `tests/test_plan94_variables_pure.py`:
- `test_f1_key_valid_and_invalid` (ok: `DEPLOY_PATH`, `_x`; error: vacía, `9X`,
  `con espacios`, `a-b`, 256 chars).
- `test_f1_secret_hints_shared_fixture` (parametrizado con el JSON: los `secret`
  dan True, los `not_secret` dan False).
- `test_f1_pure_no_io`: el texto del módulo no importa `flask` ni `requests`
  (grep del fuente — los adapters de F2 sí llaman clientes, pero vía los módulos
  provider, no éste... los adapters viven en archivos propios, ver F2).

**Ratchet:** registrar. **Criterio binario:** 3 tests (1 parametrizado ×15) verdes.
**Flag:** ninguna (puro). **Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F2 — Sub-puerto `CIVariablesProvider` + adapters GitLab y ADO

**Objetivo:** las 3 operaciones (list/set/delete) con paridad real y write-only.

**Archivo a editar:** `Stacky Agents/backend/services/ci_variables.py` — agregar:
```python
from typing import Optional, Protocol, runtime_checkable

@runtime_checkable
class CIVariablesProvider(Protocol):
    name: str
    def list_variables(self) -> list[dict]: ...
    def set_variable(self, key: str, value: str, secret: bool) -> dict: ...
    def delete_variable(self, key: str) -> bool: ...

VARIABLES_PORT_METHODS = ("list_variables", "set_variable", "delete_variable")

def get_variables_provider(project: Optional[str] = None) -> CIVariablesProvider:
    """Fábrica espejo de get_ci_provider (ci_provider.py:107) por tracker_type."""
```

**Archivo NUEVO:** `Stacky Agents/backend/services/gitlab_variables.py`
- `class GitLabVariablesProvider` (`name="gitlab"`; delegate
  `GitLabTrackerProvider(project_name=project)` y su `_request`):
  - `list_variables`: `GET /projects/:id/variables` → `[{key, is_secret:
    (masked or protected), has_value: True, masked}]` — el campo `value` de la
    respuesta del tracker se DESCARTA antes de retornar (assert en test).
  - `set_variable`: si la key existe ⇒ `PUT /projects/:id/variables/:key`, sino
    `POST /projects/:id/variables`. Body `{key, value, masked: secret,
    protected: false}`. Si el tracker responde 400 y el mensaje menciona masking
    ⇒ reintento único con `masked:false` y retorno `{"key", "is_secret": secret,
    "masked": False}`. Excepciones: relanzar `TrackerApiError` SIN el body del
    request en el mensaje (el value podría estar; sanitizar con
    `str(e)` del error del tracker solamente).
  - `delete_variable`: `DELETE /projects/:id/variables/:key`; 404 ⇒ False.

**Archivo NUEVO:** `Stacky Agents/backend/services/ado_variables.py`
- `class AdoVariablesProvider` (`name="azure_devops"`; usa `AdoClient._request`
  (`ado_client.py:257`) + `find_yaml_definition` de
  `services/ado_pipeline_definitions.py` — si ese módulo no existe aún (93/95 sin
  implementar), CREARLO con el contenido EXACTO del 93 F2):
  - Constructor resuelve `self._definition = find_yaml_definition(project)`;
    si None, TODAS las operaciones levantan
    `VariablesUnavailableError("ADO sin pipeline definition para "
    "azure-pipelines.yml — creala con 'Llevar a producción' (plan 95) o en la web "
    "de ADO")` (excepción nueva del módulo `ci_variables.py`, la captura F3 → 409).
  - `list_variables`: `GET {base_proj}/_apis/build/definitions/{id}?api-version=7.1`
    → `definition["variables"]` dict → `[{key, is_secret: bool(v.get("isSecret")),
    has_value: True, masked: None}]` (los valores de los secretos YA vienen null
    de ADO; los no-secretos se descartan igual — write-only uniforme).
  - `set_variable`: GET del detalle → merge
    `variables[key] = {"value": value, "isSecret": secret, "allowOverride": False}`
    → `PUT .../definitions/{id}` con el documento completo actualizado (ADO exige
    PUT full-definition: mismo riel GET→merge→PUT que client_profile, acá contra
    el tracker). Retorno `{"key", "is_secret": secret, "masked": None}`.
  - `delete_variable`: GET → si la key no está ⇒ False; sino `del` + PUT ⇒ True.

**Tests PRIMERO** — `tests/test_plan94_variables_providers.py` (mocks del
`_request` correspondiente en su módulo de ORIGEN; NUNCA red):
- `test_f2_factory_by_tracker_type` (patrón 93 F2).
- `test_f2_gitlab_list_never_returns_value` (fixture con `value:"S3cr3t!"` ⇒ el
  retorno NO contiene la key `value` ni el literal — centinela §3.1).
- `test_f2_gitlab_set_post_then_put` (no existe ⇒ POST; existe ⇒ PUT).
- `test_f2_gitlab_masked_rejected_fallback` (400 de masking ⇒ reintento
  `masked:false` y retorno `masked False`).
- `test_f2_gitlab_delete_404_false`.
- `test_f2_ado_no_definition_raises_unavailable` (find ⇒ None ⇒
  `VariablesUnavailableError` con "plan 95" en el mensaje).
- `test_f2_ado_list_maps_is_secret`.
- `test_f2_ado_set_merges_full_definition` (el PUT lleva el documento completo con
  la variable nueva Y las preexistentes intactas — anti-lost-update).
- `test_f2_ado_delete_absent_false`.
- `test_f2_port_structural_conformance` (patrón `test_plan73_repo_writer.py:34-44`).
- `test_f2_no_value_in_exceptions`: forzar excepción del `_request` durante
  `set_variable("K","S3cr3t!XYZ",True)` ⇒ el `str()` de la excepción propagada NO
  contiene `S3cr3t!XYZ` (patrón 91 C1).

**Ratchet:** registrar. **Criterio binario:** 11 tests verdes; grep en los 2
adapters: cero `logger`/`print` que referencien `value`.
**Flag:** ninguna (sin consumidores hasta F3). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Endpoints `/api/devops/variables` (write-only, HITL)

**Objetivo:** exponer el CRUD con guard de flag, is_json y confirm.

**Archivo NUEVO:** `Stacky Agents/backend/api/devops_variables.py` (blueprint
propio, patrón `api/devops_servers.py`; prefix SIN `/api`):
```python
bp = Blueprint("devops_variables", __name__, url_prefix="/devops/variables")

def _guard():
    if not getattr(_config.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False):
        abort(404)
    if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
        abort(400, description="Content-Type application/json requerido")  # 91 C5
```
Rutas (todas llaman `_guard()`; el project SIEMPRE en query/body):
- `GET ""?project=` → `{variables: [...], provider: "gitlab"|"azure_devops"}`;
  `VariablesUnavailableError` ⇒ 409 `{"error": <msg>, "kind":
  "variables_unavailable"}`; otra excepción ⇒ 502 `{"error": str(e)}`.
- `POST ""` body `{project, key, value, secret, confirm:true}` →
  `validate_variable_key` (400 si error); `confirm is not True` ⇒ 400 (HITL);
  `set_variable` ⇒ 201 con el retorno del provider (SIN value). PROHIBIDO loggear
  el body en cualquier rama.
- `POST "/delete"` body `{project, key, confirm:true}` → `delete_variable`;
  404 si no existía; 200 `{"ok": true}`. (POST y no DELETE para llevar body JSON
  con confirm de forma uniforme — mismo criterio que `/test` del 91.)

**Registro:** `api/__init__.py` junto a los blueprints devops existentes (import +
`api_bp.register_blueprint(devops_variables_bp)`).
**Health:** en `devops_health_route` (`api/devops.py:29-38`) agregar
`"variables_enabled": bool(getattr(cfg, "STACKY_DEVOPS_VARIABLES_ENABLED", False)),`.

**Tests PRIMERO** — `tests/test_plan94_variables_endpoints.py` (fixtures flag
on/off; provider mockeado con `unittest.mock.patch(
"api.devops_variables.get_variables_provider", ...)` — import lazy en el módulo):
- `test_f3_flag_off_all_routes_404`.
- `test_f3_non_json_post_400` (91 C5).
- `test_f3_post_without_confirm_400` (HITL server-side).
- `test_f3_post_invalid_key_400`.
- `test_f3_post_happy_201_no_value_in_response` (texto crudo sin el value).
- `test_f3_get_lists_without_values`.
- `test_f3_ado_unavailable_409_kind` (provider lanza `VariablesUnavailableError`).
- `test_f3_delete_absent_404`.
- `test_f3_health_has_variables_enabled`.
- `test_f3_route_registered` (centinela url_map).

**Ratchet:** registrar. **Criterio binario:** 10 tests verdes; grep en
`api/devops_variables.py`: cero `logger`/`print` con `value`.
**Flag:** `STACKY_DEVOPS_VARIABLES_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: sección "Variables" + "Mover a variable segura" en el builder

**Objetivo:** el candado visible y el puente 1-click desde el builder del 87.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/variablesModel.ts` (puro):
- `looksSecret(key: string): boolean` y `validateVariableKey(key): string | null`
  — ESPEJO de F1; el test de paridad lee el MISMO fixture
  `backend/tests/fixtures/plan94_secret_hints.json` (patrón 88: paridad por datos).
- `splitSpecVariables(spec): {secretLooking: string[], plain: string[]}` (inmutable).

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/VariablesSection.tsx`
- Props `{ ctx: DevOpsSectionContext }`. El gate de SU flag NO vive acá (lo
  renderiza el shell — entrada declarativa abajo).
- Lista (useQuery `["devops-variables", project]` → `DevOpsVariables.list`):
  fila = key + candado 🔒 si `is_secret` + badge "no enmascarable" si
  `masked === false` en GitLab; botón Borrar (confirm → `POST /delete`).
- Form alta: key (validación local en vivo), value (`type="password"` si el
  checkbox "secreta" está tildado), checkbox "Es secreta 🔒" (pre-tildado si
  `looksSecret(key)`), botón Guardar con `window.confirm` ⇒
  `DevOpsVariables.create({..., confirm:true})`. Value NUNCA se guarda en estado
  tras el submit (se limpia el input).
- Estado 409 `variables_unavailable` (ADO sin definición) ⇒ banner ámbar con el
  mensaje literal del backend + hint "Llevá el pipeline a producción (plan 95)".
- Errores async siempre visibles (patrón C16 87). Prohibido `console.*` único.

**Archivos a editar:**
- `frontend/src/api/endpoints.ts` — namespace nuevo `DevOpsVariables`
  (junto a `DevOps`, `endpoints.ts:3072`): `list(project)`,
  `create(body)` → POST, `remove(project, key)` → POST `/delete`.
- `frontend/src/pages/DevOpsPage.tsx` — UNA entrada declarativa en
  `DEVOPS_SECTIONS` (`:68`), shape EXACTO del contrato:
  ```ts
  {
    id: 'variables',
    label: 'Variables',
    icon: '🔒',
    healthKey: 'variables_enabled',
    gateFlagKey: 'STACKY_DEVOPS_VARIABLES_ENABLED',
    gateMessage: 'La sección Variables necesita la flag STACKY_DEVOPS_VARIABLES_ENABLED (Configuración → Arnés, categoría DevOps).',
    render: (ctx) => <VariablesSection ctx={ctx} />,
  },
  ```
  PROHIBIDO tocar el shell fuera del array (§3.12).
- `frontend/src/components/devops/PipelineBuilderSection.tsx` — si
  `ctx.health.variables_enabled === true` y `splitSpecVariables(spec).secretLooking`
  no vacío ⇒ warning ámbar "Estas variables parecen secretos y van a quedar EN EL
  YAML del repo: <keys>" + botón **"Mover a variable segura"** por key: modal con
  el value (`type="password"`, el spec solo tiene el value actual visible) →
  confirm → `DevOpsVariables.create` → al 201, quitar la key de `spec.variables`
  vía helper puro `removeSpecVariable(spec, key)` (agregar a `specBuilder.ts`,
  inmutable) → hint "Movida al tracker: usala igual, $VAR (GitLab) o $(VAR) (ADO)".
  Si `variables_enabled !== true` el warning muestra `FlagGateBanner` inline.

**Tests** — `frontend/src/devops/variablesModel.test.ts` (vitest TS puro):
- `looksSecret_shared_fixture_parity` (lee el JSON del backend, mismos 15 casos).
- `validate_key_mirror` (mismos casos que F1).
- `splitSpecVariables_detects` / `removeSpecVariable_immutable`.
Componentes: gate `tsc`.

**Criterio binario:** vitest verde (4 tests, 1 parametrizado); `tsc` 0 errores;
la entrada del registro declara `healthKey/gateFlagKey/gateMessage` y
`VariablesSection.tsx` NO contiene el literal de su flag (gate del shell — grep);
`PipelineBuilderSection.tsx` contiene el literal "Mover a variable segura".
**Flag:** `variables_enabled` (gate declarativo del shell + inline en builder).
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in (flag por UI); cargar
variables ES la feature.

### F5 — Cierre: no-regresión + checklist binario

**Comandos:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan94_variables_flag.py tests/test_plan94_variables_pure.py tests/test_plan94_variables_providers.py tests/test_plan94_variables_endpoints.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest run src/devops/variablesModel.test.ts
npx vitest run src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] Flag OFF ⇒ endpoints 404, sección con FlagGateBanner del shell, builder sin
      warning nuevo, byte-idéntico.
- [ ] PARIDAD: proyecto GitLab crea variable masked por API; proyecto ADO con
      definición crea variable `isSecret` en la definition; ADO sin definición ⇒
      409 honesto con CTA (nunca falso éxito).
- [ ] El VALUE de un secreto no aparece en: respuesta de POST, respuesta de GET,
      texto de excepciones, logs (tests centinela verdes).
- [ ] `spec.variables` con key `DB_PASSWORD` ⇒ warning + "Mover a variable segura"
      la crea en el tracker y la saca del YAML.
- [ ] GitLab masking rechazado ⇒ variable creada sin masked + badge honesto.
- [ ] Crear/borrar exige confirm server-side (400 sin él).
- [ ] `PipelineSpec`/renderers/`test_f1_spec_shape_frozen` intactos.
- [ ] Tests registrados en ambos scripts de ratchet.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Secreto fugado en excepción/log del tracker | Sanitización de excepciones (test `test_f2_no_value_in_exceptions`, patrón 91 C1) + grep centinela sin logger/print de value |
| ADO exige PUT full-definition ⇒ lost-update de variables ajenas | GET→merge→PUT dentro del adapter + `test_f2_ado_set_merges_full_definition` |
| GitLab rechaza masked por reglas de valor | Reintento `masked:false` + badge honesto en UI |
| ADO sin pipeline definition | `VariablesUnavailableError` ⇒ 409 con CTA al plan 95; la sección degrada ámbar |
| Falsos positivos de la heurística (KEYBOARD) | Regex por tokens (APIKEY/API_KEY, no KEY suelta) + fixture compartido congelado |
| Doble fuente de verdad Stacky↔tracker | El tracker ES la única fuente; Stacky no persiste nada de este plan |
| PAT sin scope (GitLab api / ADO Build RW) | TrackerApiError ⇒ 502 con mensaje visible; scopes documentados en PlainHelp |
| Bridge plan 91 (passwords de servidores → variables) | FUERA de scope v1; §3.10 del 91 sigue siendo el punto de consumo futuro (nota de compat, cero dependencia) |

## 7. Fuera de scope (v1)

- Bridge automático plan 91 → variables (nota de compatibilidad; requiere decisión
  de seguridad propia: copiar un password del Credential Manager al tracker es un
  movimiento de frontera de confianza que merece su propio plan/crítica).
- Variable groups ADO multi-pipeline (v1 usa variables de LA definition del YAML
  del panel; grupos compartidos quedan para cuando haya >1 definition).
- Scheduled rotation / expiración de secretos.
- Environments/protected branches scoping (protected:false fijo en v1).

## 8. Glosario

- **Variable masked (GitLab)**: variable CI/CD cuyo valor se oculta en los logs
  del job; exige reglas de formato del valor.
- **Variable isSecret (ADO)**: variable de la pipeline definition cifrada por ADO;
  se referencia `$(KEY)` en el YAML sin declararla.
- **Write-only**: el valor entra por POST y nunca vuelve a salir por la API.
- **Pipeline definition (ADO)**: registro del pipeline en ADO que apunta al YAML;
  prerequisito de la pata ADO (la crea el plan 95).
- **VariablesUnavailableError**: excepción del sub-puerto cuando el tracker no
  puede alojar variables todavía (ADO sin definición) → 409 `variables_unavailable`.

## 9. Orden de implementación

1. F0 — flag (5 patas).
2. F1 — helpers puros + fixture compartido de hints.
3. F2 — sub-puerto + adapters gitlab/ado (+ `ado_pipeline_definitions` si no existe).
4. F3 — blueprint endpoints + health key.
5. F4 — `variablesModel.ts` + `VariablesSection` + entrada declarativa + puente
   "Mover a variable segura" en el builder.
6. F5 — cierre.

## 10. Definición de Hecho (DoD)

- 29 tests backend nombrados (F0:5, F1:3, F2:11, F3:10) verdes por archivo con el venv.
- Vitest F4 verde; `tsc` 0 errores; paridad heurística py↔ts por fixture compartido.
- Paridad ADO+GitLab por tests de ambos adapters; degradación ADO-sin-definición
  honesta (409 + CTA).
- Ningún secreto en respuestas/logs/excepciones (centinelas verdes).
- Flag OFF ⇒ byte-idéntico; shell (`DevOpsPage.tsx`) tocado SOLO en el array
  `DEVOPS_SECTIONS`; checklist F5 completo.
