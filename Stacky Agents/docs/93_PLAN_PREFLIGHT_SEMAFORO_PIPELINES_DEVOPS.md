# Plan 93 — Preflight "¿Va a funcionar?": semáforo E2E de pipelines (ADO + GitLab)

**Estado:** CRITICADO (juez adversarial, listo para implementar)
**Versión:** v2 (v1 → v2, crítica 2026-07-05)
**Fecha:** 2026-07-05
**Serie DevOps E2E:** plan 1 de 4 (93 preflight / 94 variables / 95 producción / 96 doctor).
Los 4 planes nacen de la revisión 2026-07-04 de la serie 86-91: el panel DevOps crea,
commitea y dispara pipelines, pero NADA verifica ANTES que el pipeline vaya a
funcionar de verdad (scripts placeholder, runners inexistentes, variables sin
definir, YAML inválido para el tracker real).
**Requisito textual del operador (riel #1 de los 4 planes):** TODO compatible con
**Azure DevOps Y GitLab desde el día 1** — se harán pipelines en ambos. Prohibida
toda feature GitLab-only; donde una pata sea técnicamente inverificable, degradación
ÁMBAR honesta y explícita, jamás falso verde/rojo.
**Dependencias:** plan 87 IMPLEMENTADO (commit `84a9ecb5`) — panel DevOps host.
Planes 88-91 también implementados (`e20eee42`/`0dea09fe`/`5859ceba`/`d8b358e0`).
Verificado en working tree 2026-07-05:

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| Blueprint del panel + health con booleans aditivos | `backend/api/devops.py:22,25-38` |
| Contrato de extensión §3.12: `DEVOPS_SECTIONS` declarativo, `DevOpsSectionContext`, gate del shell | `frontend/src/pages/DevOpsPage.tsx:35,44,68` |
| `FlagGateBanner` (aviso en llano + "Activar ahora") | `frontend/src/components/devops/FlagGateBanner.tsx` |
| Builder visual + validación local + preview | `frontend/src/components/devops/PipelineBuilderSection.tsx`, `frontend/src/devops/specBuilder.ts` |
| Renderers puros spec→YAML | `backend/services/pipeline_renderers.py:23` (`to_ado_yaml`), `:126` (`to_gitlab_yaml`) |
| Validación estructural del spec (6 reglas) | `backend/services/pipeline_spec.py:112-132` |
| Fábrica por tracker_type (patrón a espejar) | `backend/services/ci_provider.py:107` (`get_ci_provider`) |
| Cliente REST ADO con PAT (helper genérico) | `backend/services/ado_client.py:257` (`_request`) |
| Cliente REST GitLab (delegate del provider) | `backend/services/gitlab_provider.py:475,522,545` |
| Literales placeholder conocidos | `starterSpec` en `frontend/src/devops/specBuilder.ts` (87 C11: `echo "reemplazar por el comando real"`); templates default plan 88 §4 (`echo "[stacky] publicar {process_name}"`, `services/publication_spec.py`) |
| Patrón flag 5 patas + gotchas | `backend/config.py:857-859`, `backend/services/harness_flags.py:177-183`, `harness_flags_help.py`, `harness_defaults.env`, ratchet `backend/scripts/run_harness_tests.ps1:103-125` |
| Namespace API frontend | `frontend/src/api/endpoints.ts:3072` (`DevOps`) |

---

## 0. Changelog v1 → v2 (crítica adversarial 2026-07-05)

Veredicto del juez: **APROBADO-CON-CAMBIOS** (0 bloqueantes, 7 importantes, 7 menores).

- **C1** F0 gana la 5ª pata que faltaba: arista `STACKY_DEVOPS_PREFLIGHT_ENABLED → STACKY_DEVOPS_PANEL_ENABLED`
  en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120-132`, junto a 88-91) + ese
  meta-test en la no-regresión. Sin esto, F0 dejaba el meta-test R4 en rojo.
- **C2** GitLab: la LISTA `GET /projects/:id/runners` NO trae `tag_list` (gotcha API real) — el matching
  por tags daba **falso rojo**. F2 ahora hidrata tags con `GET /runners/:id` por runner online (cap 20);
  detalle caído ⇒ `tags: None` y el matching degrada a `unavailable` (nunca falso rojo).
- **C3** F3: los imports de la ruta son lazy ⇒ el mock se parchea en el módulo de ORIGEN
  (`services.ci_preflight.get_preflight_provider`), NO en `api.devops` (patrón mock plan 28).
- **C4** `runners_check` (antes `_runners_check`, huérfano de fase) se especifica en F1 como función
  PURA con 4 tests nombrados propios.
- **C5** `dict_to_spec` sobre spec malformado lanzaba ⇒ 500 (violaba §3.9): ahora try/except ⇒ 400
  + test `test_f3_malformed_spec_400_never_500`.
- **C6** Contrato de check normalizado: `normalize_check` (F1, pura) completa `title/detail/fix_hint`
  y aplana `errors` — el TS `PreflightCheck` declara esos campos obligatorios.
- **C7** El centinela solo-lectura del §3.2 ahora tiene test real: `test_f3_source_scan_readonly_allowlist`
  (escaneo de fuente con allowlist de POST). El mock-based quedaba verde trivial.
- **C8** F0: nota de drift de `harness_defaults.env` (generador canónico
  `deployment/export_harness_defaults.py`; fix de drift 87-91 en curso — solo AGREGAR la línea, no revertir).
- **C9** `test_f1_placeholder_literals_frozen`: path cwd-independiente explícito (`Path(__file__)...`).
- **C10** IDs de checks fijados en el contrato F1 (`placeholders`, `variables`, `runners`).
- **C11** `target` gana valor `"auto"` (default): resuelve el tracker REAL del proyecto; `"both"` queda opt-in.
- **C12** Caps explícitos en ADO (25 pools / 50 definitions) y GitLab (20 detalles de runner) — el click no cuelga.
- **C13** `detail` de excepciones sanitizado (tokens van en headers, nunca en el mensaje; truncar a 500 chars).
- **C14** Regex GitLab excluye el escape `$$VAR` (negative lookbehind) — menos falsos warn.
- **[ADICIÓN ARQUITECTO]** Badge "Preflight: ✔/⚠/✖/– sin correr" junto a los botones commit/trigger
  + `summaryLine()` en llano (F4): cierra el KPI "0 pipelines a ciegas" sin bloquear nada (HITL intacto).
- Conteos actualizados y corregidos (el "12" de F2 v1 tenía 13 nombres): 46 tests
  backend (F0:5, F1:15, F2:15, F3:11) + 6 vitest.

## 1. Objetivo + KPI

Un botón **"¿Va a funcionar?"** en la sección Pipelines (y reusable por
Publicaciones) que corre chequeos **SOLO-LECTURA** y devuelve un **semáforo por
ítem** con mensajes en llano y hint de arreglo:

1. **Lint remoto del YAML** contra el tracker REAL (GitLab CI Lint API / ADO preview
   run) — con degradación ámbar honesta cuando ADO no tenga aún pipeline definition.
2. **Steps placeholder**: detecta scripts que siguen siendo los `echo` de ejemplo
   (starterSpec del 87, templates default del 88) → "N pasos siguen con el comando
   de ejemplo: el pipeline va a correr pero no va a desplegar nada real".
3. **Runners/agents disponibles**: verifica que exista un ejecutor online que
   matchee los `runner_tags` (GitLab) o el pool (ADO).
4. **Variables referenciadas sin definir**: `$VAR`/`${VAR}` (GitLab) y `$(VAR)`
   (ADO) usadas en scripts pero ausentes en `spec.variables` (y en las variables
   del plan 94 si su flag está ON — integración aditiva opcional).

**KPI (aspiracional; los criterios binarios están en F5):**
- 0 pipelines disparados "a ciegas": el semáforo está a 1 click antes de commit/trigger.
- 100% de los literales placeholder conocidos detectados (criterio binario F1).
- Paridad ADO+GitLab: cada check tiene su pata en ambos trackers o degrada ámbar
  con razón explícita (criterio binario F2).
- El check es 100% solo-lectura: cero efectos en tracker/repo (test centinela F3).

## 2. Por qué ahora / gap que cierra

La serie 87-91 (implementada) cubre crear→preview→commit→trigger→monitor, pero el
único feedback pre-vuelo es `_validate_spec` (`pipeline_spec.py:112-132`): 6 reglas
ESTRUCTURALES. Un pipeline estructuralmente válido puede: (a) ser YAML inválido para
el tracker (sintaxis GitLab/ADO específica vía `raw_yaml`), (b) no tener NINGÚN
runner que lo ejecute (queda `pending` eterno), (c) referenciar variables que no
existen (falla en runtime), (d) ser 100% placeholders (corre verde y no hace nada).
El operador no-experto descubre todo esto DESPUÉS de commitear/disparar. Este plan
lo adelanta a un click, antes de tocar nada.

## 3. Principios y guardarraíles (NO negociables)

1. **PARIDAD ADO + GITLAB (requisito del operador):** cada check se implementa vía
   sub-puerto `CIPreflightProvider` con DOS adapters (azure_devops y gitlab) y
   fábrica por tracker_type (espejo de `get_ci_provider`, `ci_provider.py:107`).
   Donde ADO no pueda verificar (sin pipeline definition, pool Microsoft-hosted,
   PAT sin scope), el check devuelve `status:"unavailable"` con `detail` en llano —
   NUNCA un ok/fail inventado. Tests de AMBOS adapters con mocks HTTP.
2. **Solo-lectura absoluto:** el preflight no crea, no commitea, no dispara, no
   escribe. Test centinela: el módulo backend del plan no contiene llamadas POST
   mutantes salvo las de lint/preview (que son dry-run por contrato del tracker).
3. **HITL:** el preflight INFORMA; commit y trigger siguen exigiendo sus
   confirmaciones existentes (87 F5). El semáforo NUNCA bloquea por sí solo: un
   `fail` deshabilita nada — muestra el problema y el hint (el operador decide).
4. **Flag propia** `STACKY_DEVOPS_PREFLIGHT_ENABLED`: categoría `devops`,
   `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, **SIN `default=`**
   (gotcha `_CURATED_DEFAULTS_ON`), **CON `label` y `group`** (`harness_flags.py:21-33`),
   entrada `PlainHelp`, línea en `harness_defaults.env` + test. Default OFF.
5. **Byte-idéntico con flag OFF:** endpoint 404, el botón no aparece (gate inline
   `FlagGateBanner`, patrón generator/trigger del 87 F5), cero cambio en flujos
   existentes.
6. **No degradar:** contratos de 71/72/73/87/88 intactos; `CI_PORT_METHODS`
   (`ci_provider.py:100`) NO se toca (sub-puerto NUEVO, patrón ISP del plan 73).
   `PipelineSpec` y `test_f1_spec_shape_frozen` intactos.
7. **3 runtimes:** UI + Flask; impacto NINGUNO en Codex/Claude/Copilot (se declara
   por fase).
8. **Mono-operador sin auth. Cero trabajo extra:** opt-in default OFF; usar el
   botón ES la feature. **Ratchet:** tests nuevos en `run_harness_tests.sh` y `.ps1`.
9. **Nunca 500:** toda excepción de adapter/HTTP se convierte en check
   `unavailable` con el error en `detail` (visible en UI, patrón C16 del 87).

## 4. Fases

> Comandos de test: backend `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> desde `Stacky Agents/backend` (suite completa contaminada — SIEMPRE por archivo).
> Frontend: `npx tsc --noEmit` + `npx vitest run <archivo>` en `Stacky Agents/frontend`
> (vitest instalado por 87 F3.0; NUNCA `npx vitest run` sin archivo).

### F0 — Flag `STACKY_DEVOPS_PREFLIGHT_ENABLED` (5 patas)

**Objetivo:** alta de la flag sin romper meta-tests.

**Archivos a editar (misma mecánica que 88/89/91 F0, verificada implementada):**
1. `Stacky Agents/backend/config.py` — junto a `STACKY_DEVOPS_PANEL_ENABLED`
   (`config.py:857-859`), copiando el patrón EXACTO del archivo (`.lower() in
   ("1", "true", "yes")`, SIN `.strip()` — gotcha 91 C9):
   ```python
   # Plan 93 — Preflight de pipelines DevOps. Default OFF. Editable por UI.
   STACKY_DEVOPS_PREFLIGHT_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_PREFLIGHT_ENABLED", "false"
   ).lower() in ("1", "true", "yes")
   ```
2. `Stacky Agents/backend/services/harness_flags.py`:
   - `_CATEGORY_KEYS["devops"]` (línea ~177-183): agregar
     `"STACKY_DEVOPS_PREFLIGHT_ENABLED",  # Plan 93 — preflight semáforo de pipelines`.
   - `FlagSpec` COMPLETO junto a los de la serie (después del bloque del 91):
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_PREFLIGHT_ENABLED",
         type="bool",
         label="Preflight de pipelines (Plan 93)",
         description=(
             "Plan 93 — Boton '¿Va a funcionar?' del panel DevOps: chequea el "
             "pipeline ANTES de commit/trigger (YAML valido en el tracker real, "
             "steps placeholder, runners/agents disponibles, variables sin "
             "definir) para ADO y GitLab. Solo-lectura. Default OFF: el endpoint "
             "/api/devops/preflight/check da 404 y el boton no aparece."
         ),
         group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED
         env_only=False,  # editable por UI (categoría 'devops')
         requires="STACKY_DEVOPS_PANEL_ENABLED",
     ),
     ```
     ⚠️ SIN `default=` (gotcha `_CURATED_DEFAULTS_ON`). ⚠️ SIN `reserved=`
     (consumidor real en F3).
3. `Stacky Agents/backend/services/harness_flags_help.py` — `PlainHelp` en llano
   (modelo: entrada del 87): qué hace ON ("un botón te dice si el pipeline va a
   funcionar antes de dispararlo"), OFF ("nada cambia"), ejemplo cotidiano.
4. `Stacky Agents/backend/harness_defaults.env` — línea
   `STACKY_DEVOPS_PREFLIGHT_ENABLED=false` (orden alfabético).
   ⚠️ [C8] El generador canónico del archivo es `deployment/export_harness_defaults.py`;
   hay un fix de drift 87-91 en curso en el working tree — solo AGREGAR la línea
   nueva, NUNCA revertir líneas ajenas ni regenerar el archivo completo en este plan.
5. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — [C1] agregar la
   arista al `_REQUIRES_MAP_FROZEN` (línea ~129-132, junto a las de 88-91):
   ```python
   "STACKY_DEVOPS_PREFLIGHT_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 93
   ```
   (R4 profundidad 1 OK: `STACKY_DEVOPS_PANEL_ENABLED` NO tiene `requires` — la
   arista PANEL→GENERATOR fue retirada en supervisión 2026-07-05, `harness_flags.py:1955-1957`.)

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan93_preflight_flag.py`
(espejo EXACTO de `tests/test_plan91_servers_flag.py`, cambiando la key):
- `test_f0_flag_in_registry` (`env_only is False`, `requires ==
  "STACKY_DEVOPS_PANEL_ENABLED"`, `group == "global"`, `label` no vacío,
  `default is None`).
- `test_f0_flag_in_category_devops`.
- `test_f0_config_default_off` (patrón `monkeypatch.delenv` + `importlib.reload(config)`).
- `test_f0_flag_has_plain_help`.
- `test_f0_harness_defaults_contains_flag` (literal `STACKY_DEVOPS_PREFLIGHT_ENABLED=false`).
- No-regresión: `tests/test_harness_flags.py` + `tests/test_flag_wiring.py`
  + `tests/test_harness_flags_requires.py` ([C1] la flag declara `requires` ⇒ el
  meta-test R4 exige la arista en `_REQUIRES_MAP_FROZEN`).
  (Nota centinela plan 85: si F0 se commitea sola y `test_flag_wiring.py` acusa
  flag sin consumo, implementar F0+F3 en el mismo commit — NO marcar `reserved`.)

**Ratchet:** registrar el archivo en ambos scripts (bloque `run_harness_tests.ps1:103-125`).
**Criterio binario:** 5 tests nuevos + 3 meta verdes (`test_harness_flags.py`,
`test_flag_wiring.py`, `test_harness_flags_requires.py`); default OFF.
**Flag:** `STACKY_DEVOPS_PREFLIGHT_ENABLED` (default OFF).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno (opt-in).

### F1 — Checks PUROS tracker-agnósticos (`services/pipeline_preflight.py`)

**Objetivo:** placeholders y variables-sin-definir como funciones puras
deterministas, sin I/O ni LLM.

**Archivo NUEVO:** `Stacky Agents/backend/services/pipeline_preflight.py`
```python
"""pipeline_preflight.py — Plan 93. Checks PUROS (sin I/O, sin config, sin flags).
El contrato de check es compartido por F2/F3:
{"id": str, "status": "ok"|"warn"|"fail"|"unavailable",
 "title": str_en_llano, "detail": str, "fix_hint": str}
"""
import re

# Literales EXACTOS de la serie (si 87/88 cambian sus defaults, actualizar AQUÍ
# y en el test test_f1_placeholder_literals_frozen en el mismo commit):
PLACEHOLDER_LITERALS = (
    'echo "reemplazar por el comando real"',          # 87 starterSpec (C11)
    'echo "[stacky] publicar ',                        # 88 §4 templates default (prefijo)
)

# Variables predefinidas que NUNCA cuentan como "sin definir":
_GITLAB_PREDEFINED_PREFIXES = ("CI_", "GITLAB_")
_ADO_PREDEFINED_PREFIXES = ("Build.", "Agent.", "System.", "Pipeline.", "Environment.")

# [C14] negative lookbehind: `$$VAR` es el ESCAPE de GitLab (dólar literal), no una referencia.
_GITLAB_VAR_RE = re.compile(r"(?<!\$)\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_ADO_VAR_RE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_.]*)\)")

def check_placeholders(spec_dict: dict) -> dict:
    """id FIJO: 'placeholders' [C10]. Recorre stages[].jobs[].steps[].script; un
    step es placeholder si su script (strip) es igual a un literal de
    PLACEHOLDER_LITERALS o empieza con el prefijo.
    0 matches -> status 'ok'. N>0 -> 'warn' con title
    'N paso(s) siguen con el comando de ejemplo' y fix_hint que nombra los steps
    (stage/job/step) y dice 'reemplazá el script por el comando real de deploy'."""

def referenced_variables(spec_dict: dict, target: str) -> set[str]:
    """target 'gitlab' -> _GITLAB_VAR_RE sobre cada script; 'ado' -> _ADO_VAR_RE.
    Excluye las predefinidas por prefijo (case-sensitive GitLab, case-insensitive
    ADO). PURA."""

def check_undefined_variables(spec_dict: dict, target: str,
                              defined_keys: list[str] | None = None) -> dict:
    """id FIJO: 'variables' [C10] (F3 lo re-etiqueta 'variables_{target}').
    defined = keys de spec.variables + keys de jobs[].variables + defined_keys
    (aporte OPCIONAL del plan 94 — puede ser None). Las referenciadas y no
    definidas -> 'warn' (no 'fail': pueden venir del entorno del runner) listando
    las keys; vacío -> 'ok'."""

def normalize_check(raw: dict, check_id: str, title: str) -> dict:
    """[C6] Completa el CONTRATO de check (el TS PreflightCheck declara los campos
    obligatorios): fuerza id=check_id y title=title; detail=raw.get('detail','');
    fix_hint=raw.get('fix_hint',''); si raw trae 'errors' (lint), los concatena al
    detail con '; '. Nunca devuelve keys faltantes. PURA."""

def runners_check(runners_result: dict, spec_dict: dict) -> dict:
    """[C4] id FIJO: 'runners'. Cruza los runner_tags de cada job contra los
    runners online de runners_result (contrato F2). Reglas:
    - runners_result['status'] == 'unavailable' -> propaga unavailable (mismo detail).
    - jobs SIN tags pedidos -> 'ok' si hay >=1 runner online (o hosted); 'warn' en
      llano si hay 0.
    - jobs CON tags: 'fail' "Ningún runner online atiende los tags [x, y]" si NO
      matchea ninguno; PERO si algún runner online tiene tags desconocidas
      (tags is None, ver F2 [C2]), degrada a 'unavailable' con detail en llano —
      NUNCA falso rojo.
    PURA (sin I/O)."""
```
Casos borde codificados: spec sin stages ⇒ ambos checks `ok` (la validación
estructural ya lo cubre el 87); scripts multilínea se analizan línea a línea;
`${VAR}` y `$VAR` son la misma key; `$(Build.SourceBranch)` no cuenta (predefinida).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan93_preflight_pure.py`:
- `test_f1_placeholder_starter_87_detected`: spec con el script literal del
  starterSpec ⇒ warn con "1 paso".
- `test_f1_placeholder_plan88_prefix_detected`: script
  `echo "[stacky] publicar Mul2Bane (entry)"` ⇒ warn.
- `test_f1_placeholder_real_script_ok`: script `robocopy .\out \\srv\in_ /MIR` ⇒ ok.
- `test_f1_placeholder_literals_frozen`: los literales de `PLACEHOLDER_LITERALS`
  coinciden byte a byte con `starterSpec` (leer el frontend como texto con path
  cwd-independiente [C9]: `Path(__file__).resolve().parents[2] / "frontend" /
  "src" / "devops" / "specBuilder.ts"` y assert substring) y con el default de
  `services/publication_spec.py` (`_DEFAULT_TEMPLATE`, línea 14) — centinela
  anti-drift entre planes.
- `test_f1_vars_gitlab_undefined_warn`: script `echo $DEPLOY_PATH` sin variables ⇒
  warn listando `DEPLOY_PATH`; con `spec.variables={"DEPLOY_PATH": "x"}` ⇒ ok.
- `test_f1_vars_ado_syntax`: script `copy $(DEPLOY_PATH) destino` target ado ⇒
  warn; el mismo script target gitlab ⇒ ok (sintaxis ADO no matchea regex GitLab).
- `test_f1_vars_predefined_ignored`: `$CI_COMMIT_BRANCH` (gitlab) y
  `$(Build.SourceBranch)` (ado) ⇒ ok.
- `test_f1_vars_defined_keys_from_plan94`: warn desaparece si la key viene en
  `defined_keys` (integración aditiva plan 94).
- `test_f1_vars_gitlab_escaped_dollar_ignored` [C14]: script `echo $$HOME_LIT` ⇒ ok
  (escape GitLab, no es referencia).
- `test_f1_pure_no_mutation`: spec de entrada no mutado (deepcopy previo).
- `test_f1_normalize_check_fills_contract` [C6]: raw `{"status":"fail",
  "errors":["e1","e2"],"detail":"x"}` ⇒ dict con `id/title/detail/fix_hint`
  completos y "e1; e2" dentro de `detail`; raw mínimo `{"status":"ok"}` ⇒
  `detail == ""` y `fix_hint == ""`.
- `test_f1_runners_no_tags_online_ok` [C4]: jobs sin tags + 1 runner online ⇒ ok;
  0 online ⇒ warn.
- `test_f1_runners_tags_no_match_fail` [C4]: job con `runner_tags=("deploy",)` y
  runners online con tags `["build"]` ⇒ fail con "deploy" en el mensaje.
- `test_f1_runners_tags_unknown_unavailable` [C4]: runner online con `tags: None`
  ⇒ unavailable (nunca falso rojo).
- `test_f1_runners_unavailable_propagates` [C4]: `runners_result` unavailable ⇒
  check unavailable con el mismo detail.

**Ratchet:** registrar. **Criterio binario:** 15 tests verdes.
**Flag:** ninguna (módulo puro sin consumidores hasta F3 ⇒ byte-idéntico).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F2 — Sub-puerto `CIPreflightProvider` + adapters ADO y GitLab + helper de definiciones ADO

**Objetivo:** lint remoto y runners con paridad real por tracker.

**Archivo NUEVO:** `Stacky Agents/backend/services/ci_preflight.py`
```python
"""ci_preflight.py — Plan 93. Sub-puerto ISP (patrón RepoWriter, repo_writer.py:13).
NO amplia CIProvider (CI_PORT_METHODS congelado, ci_provider.py:100)."""
from typing import Optional, Protocol, runtime_checkable

@runtime_checkable
class CIPreflightProvider(Protocol):
    name: str
    def lint_yaml(self, yaml_str: str) -> dict:
        """{'status': 'ok'|'fail'|'unavailable', 'errors': [str], 'detail': str}"""
        ...
    def list_runners(self) -> dict:
        """{'status': 'ok'|'unavailable', 'runners': [{'id', 'online': bool,
        'tags': [str]}], 'detail': str}"""
        ...

PREFLIGHT_PORT_METHODS = ("lint_yaml", "list_runners")

def get_preflight_provider(project: Optional[str] = None) -> CIPreflightProvider:
    """Fábrica espejo de get_ci_provider (ci_provider.py:107): resuelve
    tracker_type vía resolve_project_context; gitlab -> GitLabPreflightProvider,
    azure_devops -> AdoPreflightProvider; otro -> TrackerConfigError."""
```

**Archivo NUEVO:** `Stacky Agents/backend/services/ado_pipeline_definitions.py`
(helper COMPARTIDO por los planes 93/94/95 — el primero que se implemente lo crea;
los otros lo reusan si ya existe, contenido idéntico):
```python
"""ado_pipeline_definitions.py — Planes 93/94/95. Solo LECTURA en este plan.
Resuelve la pipeline definition YAML de ADO para un yaml_path dado."""
def find_yaml_definition(project: str | None, yaml_path: str = "azure-pipelines.yml") -> dict | None:
    """GET {base_proj}/_apis/build/definitions?api-version=7.1 (via
    AdoClient._request, ado_client.py:257) e itera buscando
    definition.process.yamlFilename == yaml_path (GET del detalle si la lista no
    trae process; máximo 50 definitions [C12]). Devuelve {'id': int, 'name': str}
    o None. Nunca lanza hacia arriba: TrackerApiError/errores -> None (el caller
    degrada a 'unavailable')."""
```

**Archivo NUEVO:** `Stacky Agents/backend/services/gitlab_preflight.py`
- `class GitLabPreflightProvider` (`name = "gitlab"`), constructor
  `(project: str | None)` que instancia `GitLabTrackerProvider(project_name=project)`
  (mismo patrón que `gitlab_ci_provider.py:28-30`) y usa su cliente `_request`:
  - `lint_yaml`: `POST /projects/:id/ci/lint` con `{"content": yaml_str}` →
    `valid:true` ⇒ `{"status":"ok","errors":[],"detail":"YAML válido para GitLab CI"}`;
    `valid:false` ⇒ `{"status":"fail","errors":[...del body...], ...}`. Excepción ⇒
    `{"status":"unavailable","detail":str(exc)}`.
  - `list_runners`: `GET /projects/:id/runners` — ⚠️ [C2] gotcha API GitLab: la
    LISTA **NO** trae `tag_list` (solo `GET /runners/:id` lo trae). Flujo:
    (1) listar; (2) por cada runner con `online == true` (o `status == "online"`),
    máximo 20 [C12], `GET /runners/:id` para hidratar `tag_list`; (3) si el
    detalle de UN runner falla, ese runner queda `tags: None` (desconocidas —
    `runners_check` degrada a unavailable, nunca falso rojo). Mapear
    `{id, online, tags}`. Excepción/403 de la LISTA ⇒ `unavailable` con detail
    "PAT sin scope para listar runners" si aplica.
- **Archivo NUEVO:** `Stacky Agents/backend/services/ado_preflight.py`
  - `class AdoPreflightProvider` (`name = "azure_devops"`), usa `AdoClient`:
  - `lint_yaml`: `did = find_yaml_definition(project)`; si None ⇒
    `{"status":"unavailable","detail":"ADO todavía no tiene una pipeline "
    "definition para azure-pipelines.yml — creala con 'Llevar a producción' "
    "(plan 95) o en la web de ADO; mientras tanto se valida localmente."}`;
    si existe ⇒ `POST {base_proj}/_apis/pipelines/{did}/preview?api-version=7.1`
    con `{"previewRun": true, "yamlOverride": yaml_str}` (dry-run por contrato
    ADO: NO encola). 200 ⇒ ok; 400 con mensaje de YAML ⇒ fail con el mensaje;
    otra excepción ⇒ unavailable.
  - `list_runners`: `GET {base_org}/_apis/distributedtask/pools?api-version=7.1`
    (máximo 25 pools [C12]) + por cada pool self-hosted `GET .../pools/{id}/agents` → runners
    `{id, online (status=="online" and enabled), tags: []}` (ADO no tiene tags de
    runner por agente en el modelo simple: se reporta por POOL; el matching por
    tags queda `unavailable` con detail "ADO agrupa por pool, no por tags — se "
    "verifica que el pool tenga al menos 1 agente online"). Pools hosted
    (isHosted) ⇒ entrada `{"id": ..., "online": True, "tags": ["hosted"]}` con
    nota en detail "pool Microsoft-hosted: disponibilidad no verificable, se
    asume ok (ámbar)".

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan93_preflight_providers.py`
(mocks HTTP: monkeypatch del `_request` del cliente correspondiente en su módulo de
ORIGEN — patrón 88 C7; NUNCA red real):
- `test_f2_factory_resolves_gitlab_and_ado`: monkeypatch de
  `resolve_project_context` ⇒ la fábrica devuelve el adapter correcto por
  tracker_type (patrón del test de `get_ci_provider`).
- `test_f2_gitlab_lint_ok` / `test_f2_gitlab_lint_invalid` (body con
  `valid:false, errors:["jobs config should contain at least one visible job"]`
  ⇒ fail con ese literal en errors).
- `test_f2_gitlab_runners_mapped`: fixture de LISTA (2 runners, uno online, SIN
  `tag_list` — como la API real [C2]) + fixture del DETALLE `GET /runners/:id`
  con `tag_list` ⇒ shape normalizado `{id, online, tags}` con los tags del detalle.
- `test_f2_gitlab_runner_detail_fail_tags_none` [C2]: la lista responde pero el
  detalle de un runner lanza ⇒ ese runner queda `tags: None` (no raise, no falso rojo).
- `test_f2_gitlab_exception_unavailable`: `_request` lanza ⇒ unavailable, nunca raise.
- `test_f2_ado_lint_no_definition_unavailable`: `find_yaml_definition` ⇒ None ⇒
  unavailable con "plan 95" en el detail.
- `test_f2_ado_lint_preview_ok` / `test_f2_ado_lint_preview_yaml_error_fail`.
- `test_f2_ado_pools_agents_online` / `test_f2_ado_hosted_pool_ambar`.
- `test_f2_find_definition_matches_yaml_filename` /
  `test_f2_find_definition_error_returns_none`.
- `test_f2_port_structural_conformance`: stubs con/sin métodos vs
  `isinstance(..., CIPreflightProvider)` (patrón `test_plan73_repo_writer.py:34-44`).
- `test_f2_detail_never_leaks_credentials` [C13]: los `detail` de unavailable se
  construyen con `str(exc)` truncado a 500 chars y NUNCA incluyen headers
  (`Authorization`/`PRIVATE-TOKEN`) ni el PAT — fixture con excepción que
  contiene un header falso ⇒ el detail no lo contiene (patrón 91 C1).

**Ratchet:** registrar. **Criterio binario:** 15 tests verdes (v1 decía "12" con
13 nombres — conteo corregido); grep en los 4 módulos nuevos: cero imports de
`flask` (services puros de Flask).
**Flag:** ninguna (sin consumidores hasta F3). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Endpoint `POST /api/devops/preflight/check` (solo-lectura)

**Objetivo:** orquestar F1+F2 con datos reales del proyecto; devolver el semáforo.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` (imports arriba,
patrón existente):
```python
@bp.post("/preflight/check")
def preflight_check_route():
    """Semáforo pre-vuelo. SOLO-LECTURA (no commitea, no dispara, no escribe)."""
    if not getattr(_config.config, "STACKY_DEVOPS_PREFLIGHT_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    project = body.get("project")
    spec_dict = body.get("spec")
    target = body.get("target") or "auto"      # [C11] "auto" | "ado" | "gitlab" | "both"
    if not project or not isinstance(spec_dict, dict) or target not in ("auto", "ado", "gitlab", "both"):
        return jsonify({"error": "project, spec (objeto) y target ('auto'|'ado'|'gitlab'|'both') son obligatorios"}), 400
    # [C11] "auto" = el tracker REAL del proyecto (menos ruido); fallback "both":
    if target == "auto":
        try:
            from services.project_context import resolve_project_context
            tt = resolve_project_context(project_name=project).tracker_type
            target = "gitlab" if tt == "gitlab" else "ado"
        except Exception:
            target = "both"
    checks = []
    # 1) estructural (reusa el validador del 87 — fuente de verdad)
    from services.pipeline_spec import dict_to_spec
    try:
        spec = dict_to_spec(spec_dict)
    except Exception as exc:  # [C5] spec malformado (p.ej. stages string) => 400, nunca 500
        return jsonify({"error": f"spec malformado: {exc}"}), 400
    errors = spec.validate()
    checks.append({"id": "estructura", "status": "fail" if errors else "ok",
                   "title": "Estructura del pipeline",
                   "detail": "; ".join(f"{e.field}: {e.message}" for e in errors) or "OK",
                   "fix_hint": "Resolvé los avisos del builder" if errors else ""})
    # 2) placeholders + 3) variables (F1, por target resuelto)
    from services.pipeline_preflight import (
        check_placeholders, check_undefined_variables, normalize_check, runners_check,
    )
    checks.append(check_placeholders(spec_dict))
    defined_keys = None
    # Integración ADITIVA plan 94 (si no está implementado/ON, queda None):
    if getattr(_config.config, "STACKY_DEVOPS_VARIABLES_ENABLED", False):
        try:
            from services.ci_variables import get_variables_provider
            defined_keys = [v["key"] for v in get_variables_provider(project).list_variables()]
        except Exception:
            defined_keys = None
    for t in (("ado", "gitlab") if target == "both" else (target,)):
        checks.append({**check_undefined_variables(spec_dict, t, defined_keys),
                       "id": f"variables_{t}"})
    # 4) lint remoto + 5) runners (F2, del tracker REAL del proyecto)
    if not errors:
        from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml
        from services.ci_preflight import get_preflight_provider
        try:
            provider = get_preflight_provider(project)
            yaml_str = to_ado_yaml(spec) if provider.name == "azure_devops" else to_gitlab_yaml(spec)
            lint = provider.lint_yaml(yaml_str)
            # [C6] normalize_check completa title/detail/fix_hint y aplana errors:
            checks.append(normalize_check(lint, "lint_tracker",
                                          f"YAML válido en {provider.name}"))
            runners = provider.list_runners()
            checks.append(runners_check(runners, spec_dict))  # [C4] puro, F1
        except Exception as exc:   # nunca 500 (§3.9)
            checks.append({"id": "tracker", "status": "unavailable",
                           "title": "Chequeos remotos", "detail": str(exc)[:500], "fix_hint": ""})
    summary = {s: sum(1 for c in checks if c["status"] == s)
               for s in ("ok", "warn", "fail", "unavailable")}
    return jsonify({"checks": checks, "summary": summary})
```
`runners_check` y `normalize_check` viven en `pipeline_preflight.py` (F1 [C4][C6],
con tests propios nombrados — acá solo se orquestan).
Health: agregar en `devops_health_route` (`api/devops.py:29-38`):
`"preflight_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PREFLIGHT_ENABLED", False)),`.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan93_preflight_endpoint.py`
(fixtures flag on/off patrón `test_plan87_devops_endpoints.py`; providers mockeados
con `unittest.mock.patch("services.ci_preflight.get_preflight_provider", ...)` —
⚠️ [C3] los imports de la ruta son LAZY: el patch va al módulo de ORIGEN
(`services.ci_preflight`), NUNCA a `api.devops` (patrón mock plan 28); ídem
`services.project_context.resolve_project_context` para el target "auto"):
- `test_f3_flag_off_404`.
- `test_f3_missing_params_400` (sin project / spec no-dict / target inválido).
- `test_f3_malformed_spec_400_never_500` [C5]: `spec={"stages": "no-es-lista"}` ⇒
  400 con "spec malformado", nunca 500.
- `test_f3_target_auto_resolves_tracker` [C11]: sin `target` en el body +
  `resolve_project_context` mockeado a gitlab ⇒ hay UN solo check
  `variables_gitlab` (y ninguno `variables_ado`); si `resolve_project_context`
  lanza ⇒ aparecen ambos (fallback "both").
- `test_f3_happy_path_gitlab`: spec válido + provider fake (lint ok, 1 runner
  online) ⇒ 200 con checks `estructura/placeholders/variables_*/lint_tracker/runners`,
  summary consistente y TODOS los checks con las 5 keys del contrato
  (`id/status/title/detail/fix_hint`) [C6].
- `test_f3_structural_fail_skips_remote`: spec inválido ⇒ check estructura fail y
  NO se llamó al provider (assert_not_called).
- `test_f3_provider_exception_unavailable_never_500`: provider lanza ⇒ 200 con
  check `tracker` unavailable.
- `test_f3_health_exposes_preflight_enabled`.
- `test_f3_readonly_no_writes`: `services.client_profile.save_client_profile` y
  `commit_file` de `ado_provider`/`gitlab_provider` mockeados ⇒ `assert_not_called`.
- `test_f3_source_scan_readonly_allowlist` [C7] (centinela solo-lectura REAL del
  §3.2): lee como texto los módulos nuevos del plan (`pipeline_preflight.py`,
  `ci_preflight.py`, `gitlab_preflight.py`, `ado_preflight.py`,
  `ado_pipeline_definitions.py`) y asserta que toda ocurrencia de método HTTP
  mutante (`"POST"`, `.post(`, `"PUT"`, `"PATCH"`, `"DELETE"`) esté en una línea
  cuya URL matchee la allowlist dry-run: `ci/lint` o `pipelines/.*/preview`.
  Cero excepciones.
- `test_f3_route_registered` (centinela url_map, patrón plan 74).

**Ratchet:** registrar. **Criterio binario:** 11 tests verdes + los del 87 F1
siguen verdes (health no-regresión).
**Flag:** `STACKY_DEVOPS_PREFLIGHT_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: `PreflightPanel` en la sección Pipelines (+ reuso en Publicaciones)

**Objetivo:** el semáforo visible a 1 click, en llano, sin bloquear nada.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/preflightModel.ts` (puro):
- Tipos espejo: `PreflightCheck {id, status: "ok"|"warn"|"fail"|"unavailable",
  title, detail, fix_hint}`, `PreflightResult {checks, summary}`.
- `overallStatus(checks): "ok"|"warn"|"fail"|"unavailable"` (fail > warn >
  unavailable > ok) y `sortBySeverity(checks)` (mismo orden). Inmutables.
- **[ADICIÓN ARQUITECTO]** `summaryLine(checks): string` (pura): una línea en
  llano para el operador — `"N problema(s), M aviso(s), K sin verificar"` con los
  `title` de los fail/warn concatenados; todos ok ⇒ `"Todo verde: el pipeline
  debería funcionar"`. La reusa el badge (abajo) y queda disponible para el
  doctor del plan 96 (sinergia de serie, cero costo extra).

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/PreflightPanel.tsx`
- Props: `{ ctx: DevOpsSectionContext; spec: PipelineSpecDraft; project: string;
  onResult?: (r: PreflightResult) => void }`.
- Si `ctx.health.preflight_enabled !== true` ⇒ render de `FlagGateBanner` con
  `flagKey="STACKY_DEVOPS_PREFLIGHT_ENABLED"` (patrón inline generator/trigger 87 F5).
- Botón **"¿Va a funcionar?"** ⇒ `DevOps.preflightCheck(project,
  toSpecDict(spec), "auto")` [C11]; spinner; render de checks ordenados por
  severidad con color por status (verde/ámbar/rojo/gris), `title` en negrita,
  `detail` y `fix_hint` debajo. Semáforo global arriba (`overallStatus`). Al
  recibir resultado, invoca `onResult` si vino (para el badge de abajo).
- Errores de red en try/catch hacia área visible (patrón C16 del 87). Prohibido
  `console.*` como único destino.

**[ADICIÓN ARQUITECTO] Badge "último preflight" junto a commit/trigger:**
`PipelineBuilderSection.tsx` guarda en un `useState` local el último
`PreflightResult` (vía `onResult`) y, al lado de los botones commit/trigger
existentes, muestra un badge INFORMATIVO: `Preflight: ✔ verde | ⚠ con avisos |
✖ con problemas | – sin correr`, con `summaryLine(checks)` como texto secundario.
Reglas duras: el badge NUNCA deshabilita ni bloquea los botones (HITL §3.3 — el
operador decide); si el spec se edita después del último preflight, el badge
vuelve a `– sin correr` (comparación por `JSON.stringify(toSpecDict(spec))`
memoizada — sin llamadas extra al backend). Cierra el KPI "0 pipelines
disparados a ciegas" sin agregar trabajo: el estado del pre-vuelo queda visible
exactamente donde se decide commit/trigger.

**Archivos a editar:**
- `frontend/src/api/endpoints.ts` — extender el namespace `DevOps`
  (`endpoints.ts:3072`):
  ```ts
  preflightCheck: (project: string, spec: object, target: "auto" | "ado" | "gitlab" | "both") =>
    api.post<{ checks: PreflightCheck[]; summary: Record<string, number> }>(
      "/api/devops/preflight/check", { project, spec, target }),
  ```
  (adaptar al helper HTTP real del archivo — gana el patrón del objeto `DevOps`).
- `frontend/src/components/devops/PipelineBuilderSection.tsx` — montar
  `<PreflightPanel ctx={ctx} spec={spec} project={project} />` junto al preview
  (arriba de los botones commit/trigger). CERO cambios en el shell
  (`DevOpsPage.tsx` intocado — §3.12).
- `frontend/src/components/devops/PublicationsSection.tsx` — tras materializar,
  montar el MISMO `PreflightPanel` con el spec hidratado (reuso, cero duplicación).

**Tests** — `Stacky Agents/frontend/src/devops/preflightModel.test.ts` (vitest,
TS puro): `overall_fail_wins`, `overall_ok_when_all_ok`,
`sort_by_severity_stable`, `unavailable_beats_ok`, `summary_line_counts_problems`
(1 fail + 1 warn ⇒ "1 problema" y "1 aviso" en el string),
`summary_line_all_ok` (⇒ "Todo verde"). Componentes: gate `tsc`.

**Criterio binario:** `npx vitest run src/devops/preflightModel.test.ts` verde
(6 tests) + `npx tsc --noEmit` 0 errores; grep: `PreflightPanel` aparece en
`PipelineBuilderSection.tsx` Y `PublicationsSection.tsx`; `DevOpsPage.tsx` sin
cambios (git diff vacío en ese archivo).
**Flag:** gate inline por `preflight_enabled` del health.
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in (activar flag por UI).

### F5 — Cierre: no-regresión + checklist binario

**Comandos (todos deben pasar):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan93_preflight_flag.py tests/test_plan93_preflight_pure.py tests/test_plan93_preflight_providers.py tests/test_plan93_preflight_endpoint.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_harness_flags.py tests/test_flag_wiring.py -q
cd "../frontend"
npx vitest run src/devops/preflightModel.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] Flag OFF ⇒ endpoint 404, botón ausente, byte-idéntico.
- [ ] PARIDAD: proyecto gitlab ⇒ lint CI Lint + runners con tags; proyecto ADO ⇒
      preview-run (o unavailable honesto sin definición) + pools/agents. Ningún
      check inventa ok/fail cuando no puede verificar.
- [ ] `starterSpec` sin editar ⇒ el semáforo muestra warn de placeholder
      (literal "comando de ejemplo").
- [ ] Script con `$VAR` no definida ⇒ warn que nombra la key.
- [ ] 0 runners online con tags pedidos ⇒ fail con los tags en el mensaje; tags
      DESCONOCIDAS (detalle GitLab caído) ⇒ unavailable, nunca falso rojo [C2].
- [ ] El preflight NUNCA escribe (centinela mock F3 + centinela de escaneo de
      fuente `test_f3_source_scan_readonly_allowlist` verdes) [C7].
- [ ] Checks remotos caídos ⇒ unavailable visible, nunca 500 ni bloqueo; spec
      malformado ⇒ 400, nunca 500 [C5].
- [ ] Arista `PREFLIGHT → PANEL` en `_REQUIRES_MAP_FROZEN` y
      `test_harness_flags_requires.py` verde [C1].
- [ ] Badge "último preflight" visible junto a commit/trigger, informativo, sin
      deshabilitar nada [ADICIÓN ARQUITECTO].
- [ ] Tests registrados en ambos scripts de ratchet.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| ADO sin pipeline definition ⇒ lint imposible | `unavailable` honesto con CTA al plan 95 (nunca falso verde) |
| Falsos warn de variables (vars del runner/entorno) | status `warn` (no `fail`) + allowlists de predefinidas + integración plan 94 |
| Drift de literales placeholder con 87/88 | `test_f1_placeholder_literals_frozen` (centinela cruzado) |
| PAT sin scope (runners/pools) | excepción ⇒ `unavailable` con el error (sanitizado [C13], sin headers/tokens) |
| GitLab: la LISTA de runners no trae `tag_list` [C2] | hidratación por detalle `GET /runners/:id` (cap 20); tags desconocidas ⇒ matching `unavailable`, nunca falso rojo |
| Preview-run ADO encola un run por error | `previewRun:true` es dry-run por contrato ADO; test de adapter fija el body EXACTO |
| CIProvider congelado | sub-puerto NUEVO (ISP, patrón RepoWriter) — `CI_PORT_METHODS` intacto |
| Endpoint lento (varias llamadas remotas) | solo-lectura on-demand (click), no polling; timeout del cliente HTTP existente |

## 6. Fuera de scope (v1)

- Bloquear commit/trigger por semáforo rojo (HITL: el operador decide).
- Auto-fix de placeholders (el plan 96 doctor propone fixes post-fallo; acá solo hint).
- Matching de demands/capabilities de ADO por job (v1 verifica pool con agente online).
- Cache de resultados de lint/runners (on-demand, mono-operador).

## 7. Glosario

- **Preflight**: chequeo pre-vuelo solo-lectura antes de commit/trigger.
- **CI Lint (GitLab)**: `POST /projects/:id/ci/lint` — valida un `.gitlab-ci.yml`
  sin ejecutarlo.
- **Preview run (ADO)**: `POST _apis/pipelines/{id}/preview` con `previewRun:true`
  — compila el YAML sin encolar.
- **Placeholder**: script de ejemplo generado por 87/88 que corre pero no despliega.
- **Sub-puerto (ISP)**: Protocol chico e independiente por capacidad (patrón
  `RepoWriter`, plan 73), para no tocar `CI_PORT_METHODS` congelado.
- **unavailable (ámbar)**: el check no pudo verificarse; se informa la razón, nunca
  se inventa resultado.

## 8. Orden de implementación

1. F0 — flag (5 patas, meta-tests verdes).
2. F1 — checks puros + centinela de literales.
3. F2 — sub-puerto + adapters gitlab/ado + `ado_pipeline_definitions.find_yaml_definition`.
4. F3 — endpoint + health key.
5. F4 — `preflightModel.ts` + `PreflightPanel` + integración Pipelines/Publicaciones.
6. F5 — cierre.

## 9. Definición de Hecho (DoD)

- 46 tests backend nombrados (F0:5, F1:15, F2:15, F3:11) verdes por archivo con el venv.
- Vitest F4 verde (6 tests); `npx tsc --noEmit` 0 errores.
- Meta-tests verdes: `test_harness_flags.py`, `test_flag_wiring.py`,
  `test_harness_flags_requires.py` (arista PREFLIGHT→PANEL) [C1].
- Paridad ADO+GitLab verificada por tests de ambos adapters (mocks HTTP);
  ningún check inventa ok/fail (tags desconocidas ⇒ unavailable) [C2].
- Flag OFF ⇒ byte-idéntico; checklist F5 completo.
- Ningún contrato existente modificado (solo adiciones); `DevOpsPage.tsx` intocado.
- Badge "último preflight" junto a commit/trigger, informativo (HITL) [ADICIÓN ARQUITECTO].
