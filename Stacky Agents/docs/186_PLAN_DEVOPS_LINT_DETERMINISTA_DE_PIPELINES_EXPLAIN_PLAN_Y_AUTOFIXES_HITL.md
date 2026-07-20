# Plan 186 — DevOps: lint determinista de pipelines, explain-plan y autofixes HITL

- **Versión:** v2 (CRITICADO — APROBADO-CON-CAMBIOS; v1 → v2 aplicada)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky → criticar-y-mejorar-plan)
- **Serie:** DevOps (continúa 87/88/93/96/97/99/102/103/104/116 sin duplicarlos)

## Changelog v1 → v2 (crítica C1..C9 + adiciones)

- **C1 (IMPORTANTE, falsos positivos PL005):** un job ADO `- deployment:` (usa `strategy:`, no `steps:`)
  y un job GitLab con `run:` o `extends:` ya NO se marcan como "sin pasos ejecutables". Regla reescrita
  con el conjunto EXACTO de claves ejecutables por provider + 2 tests negativos nuevos.
- **C2 (IMPORTANTE, semántica ADO):** "dependsOn ausente ⇒ depende del anterior" aplica SOLO a stages;
  los jobs dentro de un stage son PARALELOS por default (cero aristas implícitas). Afecta PL003/PL004 y
  explain-plan; test nuevo `test_kpi4_jobs_ado_paralelos_sin_dependson`.
- **C3 (IMPORTANTE, autofix PL002 renombraba la ocurrencia equivocada):** `_find_line` devuelve la
  primera coincidencia; para un duplicado eso renombraba la definición ORIGINAL y rompía los
  `dependsOn` que apuntan a ella. v2 introduce `_find_line_nth` y refuerza KPI-5: un fix NO puede
  aumentar `counts["error"]` ni introducir códigos nuevos.
- **C4 (IMPORTANTE, extracción de refs):** PL010 ya no dice "todo el texto de steps": se especifica el
  walk recursivo EXACTO sobre el árbol parseado (claves ejecutables + `env:`/`variables:`), nunca regex
  sobre el YAML crudo (los comentarios no generan refs).
- **C5 (IMPORTANTE, PL002 GitLab):** pre-scan por regex con límites DECLARADOS (claves quoteadas y
  templates `.ocultos` fuera de alcance v1, documentado) + test de no-crash con clave quoteada.
- **C6 (IMPORTANTE, race UI):** `PipelineLintPanel` lleva contador de secuencia de requests y descarta
  respuestas viejas (solo pinta la última).
- **C7 (IMPORTANTE, highlight):** instrucción concreta y retrocompatible para `PipelineYamlPreview`:
  render por líneas SOLO cuando `highlightLine` está definido; `undefined` = render actual intacto.
- **C8 (MENOR):** esqueleto F0 sin import `field` muerto; test 400 para `source` inválido agregado.
- **C9 (MENOR):** cota documentada del payload: los `fix.new_yaml` se omiten si el YAML fuente
  supera 200 KB (`findings[].fix = null` + `fixes_omitted: true` en el report).
- **[ADICIÓN ARQUITECTO 1]:** PL012 ampliado con detección determinista de PREFIJOS de tokens conocidos
  en VALORES (`ghp_`, `github_pat_`, `glpat-`, `xoxb-`, `xoxp-`, `AKIA`, `eyJhbGciOi`) — cubre el caso
  "nombre inocente, valor secreto" que la v1 no veía.
- **[ADICIÓN ARQUITECTO 2]:** selftest del catálogo de reglas (`test_plan186_lint_catalogo.py`): cada
  regla registrada declara un repro mínimo embebido que la dispara; el meta-test itera `_RULES` y falla
  si una regla queda sin repro, con código duplicado, severidad inválida o mensaje vacío. Canario
  anti-drift para cuando el catálogo crezca.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Darle a la sección DevOps un **validador determinista de pipelines** que corre
**local, offline y en milisegundos** sobre el YAML (ADO o GitLab) que el operador edita, importa o genera
en el creador gráfico: un motor de reglas con **códigos versionados (PL001..PL014)**, severidades y
mensajes en español llano; un **explain-plan** estilo `terraform plan` que muestra QUÉ va a correr, en qué
orden y con qué variables resueltas ANTES de publicar; y **autofixes con diff previo aplicados solo por
click del operador (HITL)**. Hoy el único feedback estructural previo a publicar es `spec.validate()`
(campos requeridos, `services/pipeline_spec.py:63`) y el preflight 93 (chequeos online de conexión); los
errores de estructura, dependencias rotas, variables sin declarar o secretos expuestos recién aparecen
cuando el pipeline YA falló en el servidor CI, con minutos de espera por intento. Este plan corta ese
ciclo: el error se ve en <1 segundo, con la línea exacta y el fix sugerido, sin tocar la red y sin
depender de ningún runtime LLM.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Detección | Los 12 YAML rotos del corpus del plan (6 ADO + 6 GitLab) producen ≥1 finding `error` cada uno, con el código esperado |
| KPI-2 | Cero falsos positivos | Los YAML producidos por `to_ado_yaml`/`to_gitlab_yaml` sobre los specs del corpus de `test_plan73_round_trip.py` lintean con `counts["error"] == 0`; ADO `- deployment:` y GitLab `run:`/`extends:` NO disparan PL005 |
| KPI-3 | Velocidad + pureza | Lint del corpus completo < 500 ms total, con `socket` bloqueado por monkeypatch (cero red) |
| KPI-4 | Explain-plan correcto | El caso diamante de stages A→(B,C)→D devuelve fases `[["A"],["B","C"],["D"]]` exactas; 2 jobs ADO sin `dependsOn` dentro de un stage quedan en la MISMA fase (paralelos) |
| KPI-5 | Autofix seguro (reforzado C3) | Cada autofix aplicado produce YAML que (a) parsea, (b) re-lintea sin ese código en esa línea, (c) NO aumenta `counts["error"]` total y (d) NO introduce códigos que no estaban |

**Ganancia robusta:** cada corrida CI fallida por un error detectable estáticamente cuesta 2-10 minutos de
espera + un ciclo de atención del operador. El lint elimina esa clase entera de fallos antes de publicar.

**Onboarding casi nulo:** no hay nada que configurar ni aprender: el panel de findings aparece solo dentro
del creador de pipelines existente (sección `pipelines` del panel DevOps, `DevOpsPage.tsx:99`), se
actualiza solo al editar, y cada finding se explica solo (mensaje en español + línea + fix opcional).

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `services/pipeline_spec.py:63` — `PipelineSpec.validate()` solo valida campos requeridos del spec
  (`_validate_spec`, línea 112). No mira YAML crudo, ni dependencias, ni variables, ni secretos.
- `api/devops.py:144` — `POST /devops/parse-yaml` ya parsea YAML ADO/GitLab → `PipelineSpec` (usa
  `parse_ado_yaml`/`parse_gitlab_yaml` de `services/pipeline_renderers.py:194`, plan 73 F6). O sea: los
  **parsers ya existen** y este plan los REUSA; no se escribe ningún parser nuevo.
- `api/devops.py:316` — `POST /devops/preflight/check` (plan 93) hace chequeos **online** (conexión,
  repo, credenciales). Complementario, no solapado: el lint es **offline** y estructural.
- `api/devops.py:384` — `POST /devops/doctor/diagnose` (plan 96) diagnostica fallos **después** de que el
  pipeline corrió y falló, con IA. El lint previene **antes**, sin IA.
- `api/pipeline_generator.py:34,52` — `/pipeline-generator/preview` y `/commit` (HITL `confirm=True`,
  línea 59) renderizan y commitean YAML **sin ninguna validación estructural previa**.
- Frontend: `PipelineBuilderSection.tsx`, `PipelineYamlPreview.tsx`, `CommitPipelineModal.tsx` (en
  `frontend/src/components/devops/`) muestran y commitean YAML sin feedback de calidad.

**Gap:** entre "el spec tiene los campos" (73) y "la conexión funciona" (93) falta la capa que TODA
plataforma CI seria tiene y Stacky no: análisis estático profundo del pipeline con catálogo de reglas,
explain-plan y fixes. Los planes 177-185 de la serie paralela atacan incidencias, drift de ambientes y
DB Compare; ninguno toca esto. Es el eslabón DevOps de mayor valor por esfuerzo que queda libre: puro
backend+UI, cero dependencias nuevas (PyYAML ya se usa en `services/pipeline_renderers.py`), cero
credenciales, cero LLM.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** el lint es código Python determinista + UI React.
   NO usa ningún runtime LLM (Codex CLI, Claude Code CLI, GitHub Copilot Pro): funciona idéntico con
   cualquiera de los 3 configurado, o con NINGUNO. Es la paridad más fuerte posible. Los doctores IA
   (96/104) quedan como capa complementaria opcional que sí usa runtime.
2. **Cero trabajo extra para el operador:** flag default **ON** (no aplica ninguna de las 4 excepciones
   duras: es análisis solo-lectura, sin red en el servicio, sin acciones automáticas — el autofix
   requiere click explícito). Sin pasos manuales nuevos, sin config nueva, backward-compatible: si la
   flag está OFF, todo queda EXACTAMENTE como hoy.
3. **Human-in-the-loop:** el lint NUNCA bloquea ni modifica nada solo. Los autofixes muestran diff y se
   aplican únicamente por click. El resumen en el commit modal es informativo: el operador siempre puede
   "Publicar igual".
4. **Mono-operador sin auth:** nada de roles ni permisos.
5. **No degradar:** ningún endpoint existente cambia su contrato. `commit_route`
   (`api/pipeline_generator.py:52`) NO se toca. El lint corre en la UI vía endpoint nuevo; si falla,
   la UI degrada a "lint no disponible" y el flujo actual sigue intacto.
6. **Reusar, no reinventar:** parsers de 73 (`parse_ado_yaml`/`parse_gitlab_yaml`), guard-pattern de
   `api/devops.py:147`, caja fuerte 94 (`api/devops_variables.py:46`), FlagGateBanner, CSS modules del
   panel. PyYAML ya es dependencia.
7. **Gotcha config:** en `api/devops.py` la instancia de flags es `_config.config` (el import es
   `import config as _config`); usar `getattr(_config.config, "FLAG", False)` como en la línea 147.
   NUNCA `getattr(config, ...)` sobre el módulo (mata el branch OFF).

---

## 4. Fases

### F0 — Flag, esqueleto del servicio y endpoint con guard (vertical slice)

**Objetivo:** dejar cableado flag → servicio vacío → endpoint 404/200, verificable de punta a punta.
**Valor:** el resto de las fases solo agrega reglas; el wiring queda probado desde el día 1.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- CREAR `Stacky Agents/backend/services/pipeline_lint.py`
- EDITAR `Stacky Agents/backend/api/devops.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan186_lint_flag.py`

**Cambios exactos:**

1. En `harness_flags.py`, agregar al final del bloque de FlagSpecs DEVOPS (después del bloque de
   `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED`, ~línea 2743):

```python
FlagSpec(
    key="STACKY_DEVOPS_PIPELINE_LINT_ENABLED",
    type="bool",
    label="Lint determinista de pipelines",
    description="Valida el YAML del pipeline local y al instante (reglas PLxxx), "
                "muestra el plan de ejecución y sugiere fixes con diff (HITL).",
    group="global",
    default=True,
    requires="STACKY_DEVOPS_PANEL_ENABLED",  # vive dentro del panel 87 (depth-1)
),
```

2. En el mismo archivo, agregar `"STACKY_DEVOPS_PIPELINE_LINT_ENABLED"` a `_CURATED_DEFAULTS_ON`
   (bloque DEVOPS, ~línea 200-216, con comentario `# Plan 186 — lint determinista de pipelines`).
   **Gotcha:** una FlagSpec bool default ON fuera de `_CURATED_DEFAULTS_ON` rompe
   `test_default_known_only_for_curated`.

3. CREAR `services/pipeline_lint.py` con este esqueleto EXACTO (las reglas llegan en F1-F2; C8: sin
   import `field`):

```python
"""services/pipeline_lint.py — Plan 186. Lint determinista de pipelines ADO/GitLab.

PURO: sin red, sin disco, sin config. Recibe texto y devuelve LintReport.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

ENGINE_VERSION = "186.1"

SEV_ERROR = "error"
SEV_WARNING = "warning"
SEV_INFO = "info"

# C9 — por encima de este tamaño de YAML no se adjuntan new_yaml de fixes (payload acotado)
MAX_YAML_BYTES_FOR_FIXES = 200_000


@dataclass(frozen=True)
class LintFix:
    description: str        # es-AR, 1 línea, imperativo ("Renombrar el stage duplicado a ...")
    new_yaml: str           # YAML COMPLETO corregido (cirugía de líneas, nunca re-dump)


@dataclass(frozen=True)
class LintFinding:
    code: str               # "PL001".."PL014"
    severity: str           # SEV_ERROR | SEV_WARNING | SEV_INFO
    message: str            # es-AR llano, sin jerga
    line: int | None = None # 1-based sobre el YAML fuente; None = global
    node: str | None = None # "stage:Build" | "job:test" | "var:MY_TOKEN" | None
    fix: LintFix | None = None


@dataclass(frozen=True)
class LintReport:
    ok: bool                        # True ⇔ counts["error"] == 0
    findings: tuple[LintFinding, ...]
    counts: dict                    # {"error": n, "warning": n, "info": n}
    engine_version: str
    duration_ms: float
    fixes_omitted: bool = False     # C9 — True si el YAML superó MAX_YAML_BYTES_FOR_FIXES

    def to_dict(self) -> dict:
        return asdict(self)


def lint_yaml(yaml_text: str, provider: str,
              known_variables: list[str] | None = None) -> LintReport:
    """provider: "ado" | "gitlab". known_variables: nombres de la caja fuerte 94
    (los inyecta el ENDPOINT si la UI los mandó; el servicio NO llama a la red).
    F0: devuelve reporte vacío ok=True. F1-F2 agregan reglas."""
    t0 = time.perf_counter()
    findings: list[LintFinding] = []
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f.severity] += 1
    return LintReport(
        ok=counts["error"] == 0,
        findings=tuple(findings),
        counts=counts,
        engine_version=ENGINE_VERSION,
        duration_ms=(time.perf_counter() - t0) * 1000.0,
    )
```

4. En `api/devops.py`, agregar DESPUÉS de `parse_yaml_route` (línea ~158):

```python
@bp.post("/pipeline-lint/validate")
def pipeline_lint_validate_route():
    """YAML → LintReport. PURO (el servicio no toca red); known_variables viene de la UI."""
    if not getattr(_config.config, "STACKY_DEVOPS_PIPELINE_LINT_ENABLED", False):
        abort(404)  # guard per-request, patrón devops.py:147
    body = request.get_json(silent=True) or {}
    source = body.get("source")
    yaml_str = body.get("yaml") or ""
    if source not in ("ado", "gitlab") or not yaml_str.strip():
        return jsonify({"error": "source ('ado'|'gitlab') y yaml son obligatorios"}), 400
    kv = body.get("known_variables")
    kv = [str(x) for x in kv] if isinstance(kv, list) else None
    from services.pipeline_lint import lint_yaml
    return jsonify(lint_yaml(yaml_str, source, known_variables=kv).to_dict())
```

5. Registrar el edge `STACKY_DEVOPS_PIPELINE_LINT_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` en
   `tests/test_harness_flags_requires.py` (misma estructura que las aristas DEVOPS existentes).

6. Agregar `test_plan186_lint_flag.py` a `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh`
   (**gotcha:** si no, `test_harness_ratchet_meta.py` se pone rojo).

**Tests PRIMERO** — `tests/test_plan186_lint_flag.py`:
- `test_flag_declarada_bool_default_on` — la FlagSpec existe, `type=="bool"`, `default is True`,
  `requires=="STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_flag_en_curated_defaults_on` — la key está en `_CURATED_DEFAULTS_ON`.
- `test_endpoint_404_flag_off` — con la flag OFF, `POST /api/devops/pipeline-lint/validate` → 404
  (Flask test client, patrón de `tests/test_plan87_devops_endpoints.py`).
- `test_endpoint_200_reporte_vacio_flag_on` — con flag ON (monkeypatch del atributo en
  `_config.config`), body `{"source":"ado","yaml":"stages: []\n"}` → 200 con
  `{"ok": true, "findings": [], "engine_version": "186.1", ...}`.
- `test_endpoint_400_payload_invalido` — sin `source`, sin `yaml`, Y `source:"github"` (inválido, C8)
  → 400 en los 3 casos.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan186_lint_flag.py -q`
(cwd = `Stacky Agents\backend`; SIEMPRE por archivo, nunca la suite entera).

**Criterio binario:** los 5 tests pasan Y `test_harness_ratchet_meta.py` sigue verde
(`venv\Scripts\python.exe -m pytest tests\test_harness_ratchet_meta.py -q`).

**Flag:** `STACKY_DEVOPS_PIPELINE_LINT_ENABLED`, default **ON** (ninguna excepción dura aplica:
solo-lectura, sin red, sin acción automática).

**Runtimes:** N/A al runtime LLM (backend puro). Codex/Claude/Copilot: idéntico. Fallback: flag OFF →
404 y la UI no muestra nada (comportamiento actual intacto).

**Trabajo del operador:** ninguno.

---

### F1 — Motor de reglas + source-map + reglas estructurales PL001..PL006

**Objetivo:** que el lint detecte los errores estructurales que hoy solo aparecen al fallar en CI.
**Valor:** corta la clase de fallo más frecuente (estructura/dependencias) a costo cero.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/pipeline_lint.py`
- CREAR `Stacky Agents/backend/tests/test_plan186_lint_estructura.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test nuevo)

**Diseño interno (exacto):**

```python
import re
import yaml  # PyYAML — ya es dependencia (services/pipeline_renderers.py la importa)

@dataclass
class LintContext:
    provider: str                     # "ado" | "gitlab"
    text: str                         # YAML original
    lines: list[str]                  # text.splitlines()
    data: object                      # yaml.safe_load(text) — dict | list | None
    known_variables: list[str] | None # nombres caja fuerte (F2); None = no disponible

_RULES: list = []   # [(code, severity, providers, fn, repro)]

def _rule(code: str, severity: str, providers: tuple[str, ...] = ("ado", "gitlab"),
          repro: tuple[str, str] | None = None):
    """repro: (provider, yaml_minimo_que_dispara_la_regla) — OBLIGATORIO para toda regla
    (ADICIÓN ARQUITECTO 2: el selftest del catálogo lo verifica)."""
    def deco(fn):
        _RULES.append((code, severity, providers, fn, repro))
        return fn
    return deco

def _find_line(ctx: LintContext, needle: str) -> int | None:
    """Primera línea (1-based) cuyo contenido contiene needle. Best-effort; None si no está."""
    for i, ln in enumerate(ctx.lines, start=1):
        if needle in ln:
            return i
    return None

def _find_line_nth(ctx: LintContext, needle: str, nth: int) -> int | None:
    """C3 — n-ésima línea (1-based, nth>=1) que contiene needle. None si hay menos de nth."""
    count = 0
    for i, ln in enumerate(ctx.lines, start=1):
        if needle in ln:
            count += 1
            if count == nth:
                return i
    return None
```

`lint_yaml` pasa a: (1) intentar `yaml.safe_load`; si `yaml.YAMLError` → finding único **PL001** con
`line = e.problem_mark.line + 1` si existe `problem_mark`, si no `None`, y retorna (no corre más
reglas). (2) construir `LintContext`. (3) iterar `_RULES` filtrando por provider; cada `fn(ctx)`
devuelve `list[LintFinding]`; concatenar, ordenar por `(line or 10**9, code)`, armar counts y report.
(4) C9: si `len(yaml_text.encode()) > MAX_YAML_BYTES_FOR_FIXES`, reemplazar cada finding por su copia
con `fix=None` y marcar `fixes_omitted=True`.
Toda regla va envuelta en `try/except Exception` → si una regla explota, se emite
`LintFinding(code="PL000", severity=SEV_INFO, message=f"regla {code} falló: {exc}")` y el lint NUNCA
tira 500 (robustez: un YAML raro no puede romper el editor).

**Modelo de nodos por provider (C1/C2 — EXACTO, el implementador NO infiere):**

- **ADO:** un stage = item de la lista `stages:` con clave `stage`. Un job = item de `jobs:` con clave
  `job` **o** `deployment` (los deployment jobs ejecutan vía `strategy:`, NO tienen `steps` directos).
  El "nombre" del nodo es el valor de esa clave.
  - Grafo de STAGES: `dependsOn` (str o list). **Ausente ⇒ depende del stage DECLARADO ANTERIOR**
    (semántica real de ADO). `dependsOn: []` ⇒ raíz (paralelo desde el inicio).
  - Grafo de JOBS (dentro de un stage): `dependsOn` entre jobs. **Ausente ⇒ SIN aristas (los jobs son
    PARALELOS por default en ADO)**. NUNCA agregar arista implícita job→job anterior (C2).
- **GitLab:** un job = clave top-level cuyo valor es `dict`, que NO empieza con `.` (templates ocultos)
  y NO está en las reservadas de PL006. Fases base = orden de `stages:`; `needs` agrega aristas.

**Catálogo v1 de reglas estructurales (mensajes es-AR, línea via `_find_line`):**

| Código | Sev | Provider | Detecta | Cómo (determinista) |
|--------|-----|----------|---------|---------------------|
| PL001 | error | ambos | YAML no parsea | `yaml.YAMLError` de `safe_load` |
| PL002 | error | ambos | nombre duplicado de stage/job | ADO: nombres repetidos en la lista de stages, o de jobs dentro del MISMO stage (claves `stage`/`job`/`deployment`). GitLab: `safe_load` colapsa keys duplicadas → pre-scan por línea con regex `^([A-Za-z_][\w .-]*):` sobre claves top-level NO reservadas; **límites v1 (C5, documentados):** claves quoteadas (`"x y":`) y templates `.ocultos` NO se analizan (fuera de alcance; no deben crashear ni reportar) |
| PL003 | error | ambos | dependencia a nodo inexistente | ADO: `dependsOn` (str o list) de stage/job apunta a nombre que no existe EN SU MISMO nivel (stages entre sí; jobs dentro de su stage). GitLab: `needs` (list de str o dicts con clave `job`) apunta a job inexistente |
| PL004 | error | ambos | ciclo de dependencias | DFS con pila de recursión sobre el grafo de PL003 (con la semántica de C2); reportar el ciclo como "A → B → A" |
| PL005 | error | ambos | job sin pasos ejecutables | ADO: item con clave `job` sin NINGUNA de `{steps (lista no vacía), template}`. Los items con clave `deployment` NO se evalúan (ejecutan vía `strategy`, C1). GitLab: job sin NINGUNA de `{script, run, trigger, extends}` (C1) |
| PL006 | info | ambos | clave desconocida en la raíz | ADO permitidas: `{trigger, pr, pool, variables, stages, jobs, steps, resources, parameters, name, schedules, extends, pipelines}`. GitLab reservadas: `{stages, variables, include, workflow, default, image, services, before_script, after_script, cache, pages}` — cualquier otra clave top-level cuyo valor NO sea dict (los dict son jobs) |

Notas duras para el implementador:
- ADO: si `data` no es dict o no tiene ni `stages` ni `jobs` ni `steps`, emitir PL006 info
  "estructura mínima no reconocida" y saltear PL002-PL005 (sin crashear).
- Cada regla se registra con su `repro` mínimo (ADICIÓN ARQUITECTO 2); ejemplo:
  `@_rule("PL002", SEV_ERROR, repro=("ado", "stages:\n- stage: A\n- stage: A\n"))`.

**Tests PRIMERO** — `tests/test_plan186_lint_estructura.py` (corpus INLINE en el test, strings
triple-quoted; 6 ADO rotos + 6 GitLab rotos + 2 válidos):
- `test_pl001_yaml_invalido_ado` / `..._gitlab` — YAML con tab ilegal → PL001 error con línea.
- `test_pl002_stage_duplicado_ado` / `test_pl002_job_duplicado_gitlab`.
- `test_pl002_gitlab_clave_quoteada_no_crashea` — YAML con `"mi job":` duplicado → cero excepciones,
  cero PL002 (límite documentado C5).
- `test_pl003_dependson_roto_ado` / `test_pl003_needs_roto_gitlab`.
- `test_pl004_ciclo_ado` (stages A dependsOn B, B dependsOn A) / `test_pl004_ciclo_gitlab` (needs
  cruzados).
- `test_pl005_job_sin_steps_ado` / `test_pl005_job_sin_script_gitlab`.
- `test_pl005_no_flaggea_deployment_ado` — `- deployment: X` con `strategy:` → CERO PL005 (C1).
- `test_pl005_no_flaggea_run_ni_extends_gitlab` — jobs con `run:` y con `extends:` → CERO PL005 (C1).
- `test_pl006_clave_desconocida_ambos`.
- `test_valido_ado_cero_errores` / `test_valido_gitlab_cero_errores` — `counts["error"] == 0`.
- `test_kpi2_round_trip_sin_falsos_positivos` — importar los specs del corpus de
  `tests/test_plan73_round_trip.py` (o reconstruir 2 specs mínimos con `dict_to_spec`), renderizar con
  `to_ado_yaml`/`to_gitlab_yaml` y assert `counts["error"] == 0` en ambos.
- `test_kpi3_rapido_y_sin_red` — monkeypatch `socket.socket` → `raise AssertionError("red prohibida")`;
  lintear los YAML del corpus en loop; assert duración total < 0.5 s.
- `test_regla_que_explota_no_tira_500` — monkeypatchear una regla para que lance; `lint_yaml` devuelve
  PL000 info y no propaga.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan186_lint_estructura.py -q`

**Criterio binario:** todos los tests del archivo pasan (incluye KPI-1 parcial, KPI-2, KPI-3).

**Flag:** la misma de F0 (el endpoint ya la respeta; el servicio es puro y no conoce flags).

**Runtimes:** idéntico en los 3; sin fallback necesario (no usa LLM).

**Trabajo del operador:** ninguno.

---

### F2 — Reglas de variables y secretos PL010..PL014 + selftest del catálogo

**Objetivo:** detectar variables sin declarar, muertas y secretos expuestos antes de publicar.
**Valor:** evita la 2.ª causa de pipeline roto (typo de variable) y fugas de secretos en texto plano.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/pipeline_lint.py`
- CREAR `Stacky Agents/backend/tests/test_plan186_lint_variables.py`
- CREAR `Stacky Agents/backend/tests/test_plan186_lint_catalogo.py` (ADICIÓN ARQUITECTO 2)
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar AMBOS tests)

**Extracción de referencias (C4 — walk EXACTO sobre el árbol parseado, NUNCA regex sobre el texto
crudo; los comentarios no generan refs):**

Recorrer `ctx.data` recursivamente y recolectar SOLO los valores string de:
- ADO: claves `script`, `bash`, `powershell`, `pwsh` (valor str) y TODOS los valores de dicts `env:`;
  regex de ref sobre esos strings: `\$\(([A-Za-z_][A-Za-z0-9_.]*)\)`.
- GitLab: items str de las listas `script`, `before_script`, `after_script` (a nivel job y raíz/default)
  y valores str de `variables:` de cada job; regex: `\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?`.

Declaradas: ADO `variables:` (dict o lista de `{name, value}`) a nivel raíz/stage/job; GitLab
`variables:` raíz y por job.

Whitelist predefinidas (NUNCA reportar): ADO — prefijos `Build.`, `System.`, `Agent.`, `Pipeline.`,
`Resources.`, y mayúsculas `BUILD_`, `SYSTEM_`, `AGENT_`, `PIPELINE_`, `TF_`; GitLab — prefijos
`CI_`, `GITLAB_`, más `HOME`, `PATH`, `USER`, `PWD`.

Sufijos "parece secreto": `_TOKEN`, `_PAT`, `_PASSWORD`, `_SECRET`, `_KEY`, `_APIKEY`
(case-insensitive).

[ADICIÓN ARQUITECTO 1] Prefijos de token conocidos (case-sensitive, sobre VALORES literales):
`TOKEN_VALUE_PREFIXES = ("ghp_", "github_pat_", "glpat-", "xoxb-", "xoxp-", "AKIA", "eyJhbGciOi")`.

| Código | Sev | Detecta | Regla exacta |
|--------|-----|---------|--------------|
| PL010 | warning | variable referenciada sin declarar | ref ∉ declaradas ∪ whitelist ∪ (known_variables or []) |
| PL011 | info | variable declarada nunca usada | declarada ∉ refs (solo variables de raíz; las de job pueden usarlas scripts externos → no reportar) |
| PL012 | warning | posible secreto hardcodeado | (a) valor literal de una `variables:` cuyo NOMBRE matchea sufijos secreto Y valor con ≥12 chars alfanuméricos; **(b) [ADICIÓN ARQUITECTO 1] CUALQUIER valor literal de `variables:` que empiece con un prefijo de `TOKEN_VALUE_PREFIXES` y tenga ≥12 chars** (cubre nombre inocente + valor secreto). **Gotcha push-protection:** en los TESTS construir los literales partidos (`"ghp_" + "x"*20`), nunca un token realista entero |
| PL013 | warning | secreto usado que NO está en la caja fuerte 94 | ref con sufijo secreto ∧ `known_variables is not None` ∧ ref ∉ known_variables. Si `known_variables is None` (UI no los mandó / caja fuerte no configurada) la regla SE OMITE en silencio (degradación explícita) |
| PL014 | warning | `echo` de un nombre secreto | valor str de clave ejecutable (mismo walk de C4) cuya línea contiene `echo` y una ref con sufijo secreto |

**Origen de `known_variables` (capa endpoint/UI, el servicio sigue puro):** la UI llama
`GET /api/devops/variables?project=` (endpoint EXISTENTE de la caja fuerte, `api/devops_variables.py:46`,
devuelve nombres sin valores) y pasa los nombres en `known_variables` del body de
`/pipeline-lint/validate`. Si esa llamada falla o la flag 94 está OFF → la UI manda el campo ausente y
PL013 no corre. PROHIBIDO que `pipeline_lint.py` importe `ci_variables` o toque red.

**Tests PRIMERO** — `tests/test_plan186_lint_variables.py`:
- `test_pl010_ref_sin_declarar_ado` / `..._gitlab`; `test_pl010_respeta_whitelist_ci_predefinidas`;
  `test_pl010_respeta_known_variables`.
- `test_pl010_comentario_no_genera_ref` — `# usa $(FANTASMA)` en comentario → CERO PL010 (C4).
- `test_pl011_declarada_sin_uso_info`.
- `test_pl012_secreto_por_nombre` (literal partido) / `test_pl012_valor_corto_no_reporta`.
- `test_pl012_secreto_por_prefijo_de_valor` — `MI_VAR: "ghp_" + "x"*20` → PL012 (ADICIÓN 1).
- `test_pl013_secreto_fuera_de_caja_fuerte` / `test_pl013_omitida_si_known_variables_none`.
- `test_pl014_echo_de_secreto`.

**Tests PRIMERO** — `tests/test_plan186_lint_catalogo.py` (ADICIÓN ARQUITECTO 2, selftest del
catálogo):
- `test_todo_codigo_unico` — no hay dos reglas con el mismo code.
- `test_severidades_validas` — toda severidad ∈ {error, warning, info}.
- `test_toda_regla_tiene_repro` — toda entrada de `_RULES` tiene `repro != None` (salvo PL000).
- `test_todo_repro_dispara_su_regla` — para cada `(code, _, _, _, (provider, yaml_min))`:
  `lint_yaml(yaml_min, provider)` contiene ≥1 finding con ese `code`. (Canario anti-drift: una regla
  nueva sin repro que la dispare = test rojo.)

**Comandos:** `venv\Scripts\python.exe -m pytest tests\test_plan186_lint_variables.py -q` y
`venv\Scripts\python.exe -m pytest tests\test_plan186_lint_catalogo.py -q`

**Criterio binario:** todos los tests de AMBOS archivos pasan.

**Flag:** la misma. **Runtimes:** idéntico en los 3. **Trabajo del operador:** ninguno.

---

### F3 — Autofixes deterministas con diff (datos; la UI los aplica en F5)

**Objetivo:** que cada finding fixeable traiga el YAML corregido listo para diff + apply HITL.
**Valor:** pasar de "te digo qué está mal" a "clic y queda bien", sin riesgo (preview + confirm).

**Archivos:**
- EDITAR `Stacky Agents/backend/services/pipeline_lint.py`
- CREAR `Stacky Agents/backend/tests/test_plan186_lint_fixes.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Regla de oro de los fixes:** **cirugía de líneas sobre `ctx.lines`** (insertar/reemplazar/borrar
líneas puntuales y `"\n".join(...)`), NUNCA `yaml.safe_dump` (re-dump destruye formato y comentarios
del operador). Cada fix se construye solo si la línea objetivo se localizó; si no, `fix=None`.

| Código | Fix determinista |
|--------|------------------|
| PL002 | Renombrar la SEGUNDA ocurrencia agregando sufijo `-2`. **C3: localizar con `_find_line_nth(ctx, needle, 2)`** (la 1.ª ocurrencia — la definición original que otros nodos referencian — NO se toca) |
| PL003 | Quitar la referencia rota de `dependsOn`/`needs` (si la lista queda vacía, borrar la clave completa de esa línea) |
| PL005 | Insertar debajo de la línea del job, con la indentación del bloque: ADO `steps:` + `- script: echo "TODO reemplazar"`; GitLab `script:` + `- echo "TODO reemplazar"` |

PL001/PL004/PL006/PL010-PL014: `fix=None` en v1 (decisión explícita: fixes de semántica ambigua NO se
automatizan).

**Tests PRIMERO** — `tests/test_plan186_lint_fixes.py`:
- Por cada fix (PL002 ADO, PL002 GitLab, PL003 ADO, PL003 GitLab, PL005 ADO, PL005 GitLab), KPI-5
  reforzado (C3): `fix.new_yaml` (a) parsea con `yaml.safe_load`, (b) re-lint NO contiene ese código en
  esa línea, **(c) `counts["error"]` del re-lint es MENOR que el del original, (d) el re-lint NO
  contiene códigos que el original no tenía**, (e) el resto del texto quedó idéntico salvo las líneas
  tocadas (comparar `difflib.unified_diff` → ≤ 3 líneas cambiadas).
- `test_fix_pl002_renombra_la_segunda_no_la_primera` — YAML ADO con `A` duplicado y un tercer stage con
  `dependsOn: A` → tras el fix, ese `dependsOn` sigue resolviendo (cero PL003 nuevos) (C3).
- `test_fix_none_si_linea_no_localizada` — YAML donde la línea no se localiza → `fix is None`, sin
  crash.
- `test_fixes_omitidos_yaml_gigante` — YAML > 200 KB (generado por código en el test) → todos los
  `fix is None` y `fixes_omitted is True` (C9).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan186_lint_fixes.py -q`

**Criterio binario:** todos los tests pasan (KPI-5 completo).

**Flag:** la misma. **Runtimes:** idéntico. **Trabajo del operador:** ninguno (aplicar un fix es
opcional y por click, F5).

---

### F4 — Explain-plan: simulación del orden de ejecución

**Objetivo:** mostrar QUÉ va a correr, en qué orden/paralelismo y con qué variables, antes de publicar.
**Valor:** el operador entiende el pipeline de un vistazo (estilo `terraform plan`), sin correr nada.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/pipeline_lint.py`
- EDITAR `Stacky Agents/backend/api/devops.py`
- CREAR `Stacky Agents/backend/tests/test_plan186_explain_plan.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Diseño (exacto):**

```python
@dataclass(frozen=True)
class PlanNode:
    kind: str                    # "stage" | "job"
    name: str
    steps: tuple[str, ...]       # display names de los pasos (script truncado a 80 chars)
    resolved_vars: dict          # solo resolución LITERAL (var → valor si el valor no referencia otra var)
    warnings: tuple[str, ...]    # p.ej. "condicional: puede no ejecutarse"
    estimated_seconds: float | None  # SIEMPRE None en v1 (campo reservado, documentado; sin histórico NO se inventa)

@dataclass(frozen=True)
class ExecutionPlan:
    phases: tuple[tuple[PlanNode, ...], ...]  # fases en orden; dentro de una fase, paralelo
    provider: str
    ok: bool                                  # False si hay ciclo (PL004) → phases vacío

def explain_plan(yaml_text: str, provider: str) -> ExecutionPlan: ...
```

- Grafo con la MISMA semántica de F1/C2: ADO stages secuenciales-por-default (`dependsOn` explícito
  manda; `[]` = raíz), **jobs ADO paralelos por default (cero aristas implícitas)**, items
  `deployment` son jobs válidos; GitLab fases base = orden de `stages:`, `needs` adelanta jobs.
- Fases = niveles topológicos (Kahn), orden alfabético DENTRO de cada fase (determinismo del output).
  Ciclo → `ok=False`, `phases=()` (el lint ya lo reporta PL004).
- `resolved_vars`: SOLO variables cuyo valor es literal (sin `$`); lo demás se muestra como
  `"<dinámica>"`. Sin evaluación de shell, sin condiciones: si un nodo tiene `condition:`/`rules:` se
  agrega warning `"condicional: puede no ejecutarse"`.
- Endpoint en `api/devops.py`, mismo guard y shape que validate:
  `@bp.post("/pipeline-lint/explain")` → `{"plan": asdict(ExecutionPlan)}`; 400 si payload inválido.

**Tests PRIMERO** — `tests/test_plan186_explain_plan.py`:
- `test_kpi4_diamante_stages_ado` — A; B dependsOn A; C dependsOn A; D dependsOn [B,C] → fases
  `[["A"],["B","C"],["D"]]` (nombres exactos, orden alfabético dentro de la fase).
- `test_kpi4_jobs_ado_paralelos_sin_dependson` — stage con jobs J1, J2 sin dependsOn → AMBOS en la
  misma fase (C2).
- `test_deployment_job_aparece_en_plan` — `- deployment: X` figura como PlanNode kind="job" (C1).
- `test_gitlab_stages_y_needs` — 3 stages, un job con `needs` del stage 1 queda en fase 2.
- `test_ciclo_ok_false` — ciclo → `ok is False`, `phases == ()`.
- `test_vars_literales_resueltas` — literal → valor; compuesta → `"<dinámica>"`.
- `test_condicional_warning`.
- `test_endpoint_explain_404_off_200_on` (patrón F0).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan186_explain_plan.py -q`

**Criterio binario:** todos los tests pasan (KPI-4 completo).

**Flag:** la misma. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F5 — UI: panel de findings en el creador, highlight de línea y apply-fix con diff (HITL)

**Objetivo:** que todo lo anterior aparezca solo, dentro del creador de pipelines, sin pasos nuevos.
**Valor:** onboarding cero — el operador ve findings/plan/fix donde ya trabaja.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/devops/PipelineLintPanel.tsx`
- CREAR `Stacky Agents/frontend/src/components/devops/PipelineLintPanel.module.css`
- CREAR `Stacky Agents/frontend/src/components/devops/pipelineLint.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/devops/pipelineLint.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx` (montar el panel)
- EDITAR `Stacky Agents/frontend/src/components/devops/PipelineYamlPreview.tsx` (prop nueva OPCIONAL
  `highlightLine?: number` — retrocompatible, default undefined = comportamiento actual)

**Comportamiento exacto:**
1. `pipelineLint.ts` exporta (puras, testeables sin DOM):
   - `groupFindings(findings) -> {errors, warnings, infos}` (ordenadas por línea).
   - `buildDiffLines(oldYaml, newYaml) -> {added: number[], removed: number[], rows: DiffRow[]}`
     (diff lineal simple LCS por líneas; `DiffRow = {kind: 'same'|'add'|'del', text: string}`).
   - `debounceKey(yaml, source) -> string` (hash simple djb2 para evitar requests repetidos).
   - `commitLintSummary(report | undefined)` (F6; definido acá para testear puro).
2. `PipelineLintPanel` recibe props `{yaml: string, source: 'ado'|'gitlab', knownVariables?: string[],
   onHighlightLine: (n: number|undefined) => void, onApplyFix: (newYaml: string) => void}`:
   - `useEffect` con debounce 500 ms sobre `yaml`: `POST /api/devops/pipeline-lint/validate`; si la
     respuesta es 404 (flag OFF) el panel se auto-oculta (render `null`).
   - **C6 (anti-race):** mantener `const seqRef = useRef(0)`; cada request incrementa y captura
     `const seq = ++seqRef.current`; al resolver, si `seq !== seqRef.current` → DESCARTAR la respuesta
     (solo la última pinta). Sin esto, dos validates in-flight pueden pintar findings viejos.
   - Render: 3 chips con conteos (`error` rojo, `warning` ámbar, `info` gris — tokens del
     `DevOpsPage.module.css`; **gotcha ratchet:** CERO `style={{}}` inline en .tsx nuevo, todo por
     CSS module), lista de findings `[PLxxx] mensaje — línea N`, click → `onHighlightLine(line)`.
   - Finding con `fix`: botón "Ver fix…" abre un `<details>` inline con el diff (filas de
     `buildDiffLines`, clases `.add`/`.del`) y botón "Aplicar este fix" → `onApplyFix(fix.new_yaml)`.
     El apply SOLO pisa el textarea del builder (estado local): el operador después
     guarda/commitea por el flujo existente (HITL intacto, nada se publica solo).
   - Botón "Plan de ejecución" → `POST /pipeline-lint/explain`, render de fases como lista numerada
     ("Fase 1: A — Fase 2: B ∥ C — Fase 3: D") con warnings por nodo.
3. `PipelineBuilderSection.tsx`: montar `<PipelineLintPanel …/>` inmediatamente DEBAJO de
   `PipelineYamlPreview`, pasando el YAML activo y la fuente seleccionada; `knownVariables` se
   obtiene con un `fetch` único a `/api/devops/variables?project=` (si !ok → undefined). Un solo
   punto de integración; si la flag está OFF el panel devuelve null y el builder queda idéntico.
4. **C7 — `highlightLine` en `PipelineYamlPreview.tsx` (instrucción concreta y retrocompatible):**
   ANTES de editar, leer el componente. Si renderiza el YAML como string único (p.ej. dentro de un
   `<pre>`), aplicar esta técnica: cuando `highlightLine === undefined`, render EXACTAMENTE igual que
   hoy (cero cambio); cuando está definido, `yaml.split('\n')` y renderizar `<div>` por línea (misma
   fuente monoespaciada vía CSS module), agregando a la línea `highlightLine - 1` la clase
   `.lineHighlight` (fondo con el token de acento del module) y `ref` con
   `scrollIntoView({block:'center'})` en un `useEffect` que depende de `highlightLine`.

**Tests PRIMERO** — `pipelineLint.test.ts` (vitest, **sin @testing-library** — no está en
`package.json` (gap conocido); espejar el estilo de `RemediationCard.test.tsx`: solo funciones puras):
- `groupFindings` ordena y agrupa por severidad.
- `buildDiffLines` marca add/del correctas en un caso de 1 línea reemplazada y 2 insertadas.
- `debounceKey` cambia si cambia yaml o source, estable si no.

**Comando:** `npx vitest run src/components/devops/pipelineLint.test.ts`
(cwd = `Stacky Agents\frontend`; SIEMPRE por archivo — gotcha contaminación cross-file).

**Criterio binario:** los 3 tests pasan Y `npx tsc --noEmit` (cwd frontend) sin errores nuevos.

**Flag:** la misma (el panel se auto-oculta con 404). **Runtimes:** idéntico (UI pura).
**Trabajo del operador:** ninguno — el panel aparece solo; aplicar fixes es opcional por click.

---

### F6 — Resumen de lint en el modal de commit (informativo, NUNCA bloquea)

**Objetivo:** que el último LintReport sea visible EXACTAMENTE en el momento de decidir publicar.
**Valor:** decisión informada sin fricción nueva; HITL enriquecido, no endurecido.

**Archivos:**
- EDITAR `Stacky Agents/frontend/src/components/devops/CommitPipelineModal.tsx`
- EDITAR `Stacky Agents/frontend/src/components/devops/PipelineBuilderSection.tsx` (pasar el último
  `LintReport` al modal como prop OPCIONAL `lintReport?: LintReport`)
- CREAR `Stacky Agents/frontend/src/components/devops/commitLintSummary.test.ts`
- (backend: **CERO cambios** — `commit_route` de `api/pipeline_generator.py:52` NO se toca)

**Comportamiento exacto:**
- Si `lintReport` es undefined → el modal queda IDÉNTICO a hoy (retrocompatible).
- Si `counts.error > 0` → banda roja arriba del confirm: "El lint encontró N errores. Podés publicar
  igual, pero es probable que el pipeline falle." y el botón de confirmar cambia su texto a
  "Publicar igual (N errores)". **El botón NUNCA se deshabilita** (HITL manda; guardarraíl §3.3).
- Si solo warnings → banda ámbar "N advertencias del lint". Si ok → línea verde "Lint OK (PLxxx v186.1)".
- Helper puro `commitLintSummary(report | undefined) -> {tone: 'ok'|'warn'|'error'|'none',
  text: string, confirmLabel: string | null}` YA exportado desde `pipelineLint.ts` (F5) — el modal
  solo lo renderiza.

**Tests PRIMERO** — `commitLintSummary.test.ts` (vitest, funciones puras):
- undefined → `tone:'none'`, `confirmLabel:null` (modal intacto).
- report con 2 errores → `tone:'error'`, `confirmLabel:"Publicar igual (2 errores)"`.
- report solo warnings → `tone:'warn'`. — report limpio → `tone:'ok'`.

**Comando:** `npx vitest run src/components/devops/commitLintSummary.test.ts`

**Criterio binario:** los 4 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Flag:** la misma (sin report no hay banda). **Runtimes:** idéntico.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Falsos positivos que erosionen confianza | KPI-2 como gate binario (round-trip renderers → 0 errores + casos deployment/run/extends); severidades conservadoras (PL006/PL011 = info; variables = warning, nunca error); PL013 se omite sin datos |
| Catálogo de claves ADO/GitLab incompleto | PL006 es `info` (no asusta); catálogo en constantes módulo-nivel; regla envuelta en try/except (PL000); selftest del catálogo exige repro por regla (ADICIÓN 2) |
| Fix rompe un YAML exótico | KPI-5 reforzado (C3): re-parsea, re-lintea, no aumenta errores NI introduce códigos nuevos; cirugía ≤3 líneas; diff SIEMPRE visible antes de aplicar |
| Parsers del plan 73 cubren un subset | El lint NO depende de `parse_*_yaml` para las reglas (trabaja sobre `yaml.safe_load` crudo); los parsers solo se reusan donde ya se usaban (parse-yaml editor) |
| Sesión paralela toca `api/devops.py` (serie 177-185 activa) | Cambios ADITIVOS al final de secciones (endpoint nuevo tras `parse_yaml_route`); tras merge correr `python -m compileall` + grep del duplicado silencioso (gotcha conocido) |
| Regex de secretos (PL012) dispara push-protection de GitHub en los tests | Literales SIEMPRE partidos en tests (`"ghp_" + "x"*20`) — gotcha documentado |
| Respuestas stale pintan findings viejos (UI) | C6: contador de secuencia; solo la última respuesta pinta |
| `test_*.py` nuevo no registrado | Cada fase que crea un test EDITA `run_harness_tests.sh` en el mismo commit; `test_harness_ratchet_meta.py` lo verifica |

## 6. Fuera de scope (explícito)

- Ejecutar steps localmente (sandbox de ejecución real) — solo simulación estática.
- Estimación de duraciones con histórico del monitor 103 (`estimated_seconds` queda reservado en el
  shape, SIEMPRE None en v1).
- Resolución de `include:`/`template:` remotos (v1: si aparecen, PL006-info "include no resuelto").
- `needs` hacia stages posteriores en GitLab (validación semántica fina de GitLab): v1 solo chequea
  existencia; la validación de dirección queda para v2.
- Claves quoteadas y templates `.ocultos` en el pre-scan PL002 GitLab (límite C5 documentado).
- Wiring del lint como tool del agente DevOps (90/108) — el endpoint queda documentado y disponible.
- Lint de pipelines internos de Stacky (`api/pipelines.py` es el orquestador interno, otro dominio).
- Bloqueo del commit por errores (contradice HITL; solo informativo).

## 7. Glosario (para modelos menores)

- **ADO:** Azure DevOps. **GitLab CI:** su equivalente en GitLab (`.gitlab-ci.yml`).
- **Deployment job (ADO):** item `- deployment: X` en `jobs:`; ejecuta vía `strategy:`, no tiene
  `steps:` directos — NO es un job roto.
- **PipelineSpec:** modelo declarativo interno de Stacky (`services/pipeline_spec.py:55`).
- **Renderers/parsers 73:** `to_ado_yaml`/`to_gitlab_yaml` y `parse_ado_yaml`/`parse_gitlab_yaml` en
  `services/pipeline_renderers.py` (ida y vuelta YAML↔spec).
- **Caja fuerte (94):** variables CI guardadas en el tracker; `GET /api/devops/variables` lista NOMBRES
  sin valores (`api/devops_variables.py:46`).
- **Preflight (93) / Doctor (96):** chequeos online previos / diagnóstico IA post-fallo. El lint es la
  capa offline previa a ambos.
- **HITL:** human-in-the-loop — toda acción con efecto la confirma el operador.
- **Flag del arnés:** entrada en `FLAG_SPECS` (`services/harness_flags.py`) configurable desde la UI.
- **`_CURATED_DEFAULTS_ON`:** lista blanca de flags bool con default ON (si falta, meta-test rojo).
- **HARNESS_TEST_FILES:** registro de tests del arnés en `backend/scripts/run_harness_tests.sh`;
  olvidarlo pone rojo `test_harness_ratchet_meta.py`.
- **Ratchet UI:** guardia que impide `style={{}}` inline en `.tsx` nuevos — usar CSS modules.
- **Cirugía de líneas:** editar el YAML tocando líneas puntuales, nunca re-serializar todo.
- **Repro (catálogo):** YAML mínimo registrado junto a cada regla que la dispara; el selftest lo
  verifica (ADICIÓN 2).

## 8. Orden de implementación

1. F0 — flag + esqueleto + endpoint validate + tests de wiring (vertical slice completo).
2. F1 — motor de reglas + PL001..PL006 (semántica C1/C2) + corpus + KPI-2/KPI-3.
3. F2 — PL010..PL014 (variables/secretos, walk C4) + selftest del catálogo (ADICIÓN 2).
4. F3 — autofixes PL002/PL003/PL005 (`_find_line_nth`, C3) + KPI-5 reforzado.
5. F4 — explain_plan (semántica C2) + endpoint explain + KPI-4.
6. F5 — PipelineLintPanel (anti-race C6) + helpers puros + integración builder + highlight (C7).
7. F6 — resumen en CommitPipelineModal.

Cada fase se commitea sola, con sus tests verdes ANTES de pasar a la siguiente (TDD estricto, cero
falsos verdes: si un test no corre, se reporta rojo, no se lo salta).

## 9. Definición de Hecho (DoD) global

- [ ] Los 8 archivos de test del plan (`test_plan186_lint_flag.py`, `test_plan186_lint_estructura.py`,
      `test_plan186_lint_variables.py`, `test_plan186_lint_catalogo.py`, `test_plan186_lint_fixes.py`,
      `test_plan186_explain_plan.py`, `pipelineLint.test.ts`, `commitLintSummary.test.ts`) pasan
      corriendo POR ARCHIVO con el intérprete/venv correcto
      (`venv\Scripts\python.exe -m pytest tests\<archivo> -q` / `npx vitest run <archivo>`).
- [ ] `test_harness_ratchet_meta.py`, `test_harness_flags_requires.py` y
      `test_default_known_only_for_curated` (en `test_harness_flags.py`) siguen verdes.
- [ ] KPI-1..KPI-5 verificados por los tests nombrados (binarios, con los refuerzos C1/C2/C3).
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio.
- [ ] Flag `STACKY_DEVOPS_PIPELINE_LINT_ENABLED` visible y toggleable desde la UI de flags (grupo
      global, requires panel 87), default ON.
- [ ] Con la flag OFF: cero diferencias observables vs. hoy (404 endpoint, panel ausente, modal
      idéntico).
- [ ] Ningún endpoint/contrato existente modificado (`commit_route`, `parse-yaml`, preflight, doctor
      intactos).
- [ ] Cero llamadas de red desde `services/pipeline_lint.py` (test KPI-3 lo prueba).
