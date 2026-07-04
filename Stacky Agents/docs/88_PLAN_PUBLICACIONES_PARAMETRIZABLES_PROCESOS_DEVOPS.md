# Plan 88 — Publicaciones parametrizables de procesos batch/agenda/TODO desde el panel DevOps

**Estado:** PROPUESTO
**Versión:** v1 → v2 (crítica adversarial `criticar-y-mejorar-plan`, 2026-07-04)
**Fecha:** 2026-07-03 (v1) / 2026-07-04 (v2)
**Serie DevOps:** plan 2 de 3.
**Dependencias:** plan 87 (`87_PLAN_PANEL_DEVOPS_CREADOR_GRAFICO_PIPELINES.md`,
**en su versión v2**, commit `e533c283` — panel DevOps base; la v1 `59918622` quedó
superada). Este plan agrega la sección **Publicaciones** a `DEVOPS_SECTIONS` (punto de
extensión del plan 87 v2 F4: `render(ctx: DevOpsSectionContext)`). El plan 3 de la
serie (inicialización de ambientes, plan 89) dependerá de ÉSTE (reusa el
materializador). Además requiere implementados los planes 45/71/72/73 — VERIFICADO:

| Pieza existente | Evidencia (archivo:línea) |
|---|---|
| process_catalog editable por UI + allowlist kinds | `backend/api/client_profile.py:57` (`ALLOWED_PROCESS_KINDS = {"entry","processing","output"}`), `:138-156` |
| GET/PUT client_profile (el PUT **REEMPLAZA el profile completo**) | `backend/api/client_profile.py:94,127,161` |
| Loader/saver reales de client_profile | `backend/services/client_profile.py:266` (`load_client_profile`), `:315` (`save_client_profile`); `api/client_profile.py:34` importa de `services.client_profile` |
| Loader del catálogo | `backend/api/agents.py:1436` (`_load_process_catalog`) |
| PipelineSpec + dict_to_spec + validate | `backend/services/pipeline_spec.py:55,69,112` |
| Renderers YAML | `backend/services/pipeline_renderers.py:23,126` |
| POST /api/pipeline-generator/preview y /commit (HITL) | `backend/api/pipeline_generator.py:34,52,59-60` |
| Trigger/monitor CI HITL | `backend/api/ci.py:26,76,139,174` |
| Panel DevOps: `DEVOPS_SECTIONS` con `render(ctx)`, `api/devops.py`, flag master | plan 87 v2 F1/F4 (`frontend/src/pages/DevOpsPage.tsx`, `backend/api/devops.py`) |
| FlagSpec: `label` y `group` son campos REQUERIDOS | `backend/services/harness_flags.py:21-33` (87 v2 C3) |
| Pata de deploy de flags nuevas | `backend/harness_defaults.env` + patrón de test `tests/test_plan75_deep_links_wiring.py:50-58` |

> **Nota de secuencia:** si al implementar este plan el 87 (v2) aún no está
> implementado, implementarlo primero. Este doc NO redefine nada del 87; solo lo
> extiende. Este plan fue reescrito contra el **87 v2** (contratos: `render(ctx)`,
> GET→merge→PUT, vitest instalado en 87 F3.0, `api.get/api.post` con path `/api/...`).

## CHANGELOG v1 → v2

- **C1 (BLOQUEANTE, resuelto):** F5 v1 registraba la sección con
  `render: () => <PublicationsSection />` y decía "el health ya viene del contexto de
  DevOpsPage; pasarlo por prop" (vago). El contrato del 87 v2 (FIX C4/C9 de aquel plan)
  es `render: (ctx: DevOpsSectionContext) => ReactNode`. v2 fija literal:
  `render: (ctx) => <PublicationsSection ctx={ctx} />` + ampliación ADITIVA de
  `DevOpsHealth` con la key opcional `publications_enabled?: boolean`.
- **C2 (BLOQUEANTE, resuelto):** F5 v1 decía "guardar = PUT client-profile con la lista
  actualizada" sin fijar el flujo. `put_client_profile` REEMPLAZA el profile completo
  (`api/client_profile.py:161`): un modelo menor habría PUTeado solo
  `{"devops_publication_presets": [...]}` y BORRADO `process_catalog` y el resto de la
  config del operador — exactamente el C1 del 87 v2, que este plan repite en 3 keys
  (presets, settings, publish_group). v2 impone el riel **GET → merge → PUT** (§3.9)
  con helper puro `mergeKeysIntoProfile` testeado (F4) y flujo literal en F5.
- **C3 (IMPORTANTE, resuelto):** el snippet `FlagSpec` de F0 v1 omitía `label` y
  `group`, campos REQUERIDOS del dataclass (`harness_flags.py:21-33`) ⇒ TypeError al
  importar. Repetía el C3 del 87 v1 ya corregido allí. v2 trae el snippet completo.
- **C4 (IMPORTANTE, resuelto):** contradicción interna: F2 v1 decía "nombres duplicados
  NO se validan; la UI usa el último", pero el endpoint F3 usa `next(...)` = toma el
  PRIMERO. Además, incoherente con el propio 87 v2 C7 (drafts: únicos, cap 50, ≤120
  chars). v2 valida en F2: `name` único, ≤120 chars, máximo 50 presets (+3 tests).
- **C5 (IMPORTANTE, resuelto):** presets corruptos ⇒ 500: si
  `devops_publication_presets` del profile guardado (editable también por JSON directo)
  no es lista o contiene no-dicts, `next((p for p in presets if p.get("name")...))`
  lanza AttributeError ⇒ 500. v2: filtro defensivo en el endpoint + entradas no-dict del
  catálogo ignoradas en el módulo puro + test "nunca 500".
- **C6 (IMPORTANTE, resuelto):** el comentario del snippet de `endpoints.ts` en F4 v1
  decía `POST /devops/publications/materialize` sin el prefijo `/api` — contradice el
  FIX C5 del 87 v2 (`api.post` con path COMPLETO `/api/...`). v2 trae el snippet
  literal con `"/api/devops/publications/materialize"`.
- **C7 (IMPORTANTE, resuelto):** `test_f3_readonly_no_writes` v1 pedía "mockear el
  saver EN EL MÓDULO api.devops" — `api/devops.py` NUNCA importa `save_client_profile`
  ⇒ `patch("api.devops.save_client_profile")` lanza AttributeError. Además F3 v1
  dejaba "verificar el nombre real de load_client_profile con grep antes de escribir"
  (inferencia prohibida). v2 resuelve ambos: VERIFICADO — importar
  `from services.client_profile import load_client_profile`
  (`services/client_profile.py:266`); el saver se patchea en su módulo de ORIGEN
  (`services.client_profile.save_client_profile`).
- **C8 (IMPORTANTE, resuelto):** faltaba la pata de deploy de la flag:
  `backend/harness_defaults.env` (snapshot horneado en `backend\.env` en cada deploy).
  Causa raíz RECURRENTE: los planes 74 y 75 tuvieron que corregirlo post-hoc en
  supervisión (patrón `test_plan75_deep_links_wiring.py:50-58`). v2: F0 agrega la línea
  `STACKY_DEVOPS_PUBLICATIONS_ENABLED=false` + test dedicado.
- **C9 (MENOR, resuelto):** el preámbulo de fases citaba "plan 87 §F4" para los
  comandos de test; en el 87 v2 los comandos viven en el preámbulo de §4 y vitest se
  instala en **F3.0** (devDependency). v2 corrige la referencia y prohíbe re-instalar.
- **C10 (MENOR, resuelto):** `resolvePreview` v1 decía "espejo TS de resolve_processes
  (misma semántica)" pero devolvía `excluded`, que el backend NO computa, y no devolvía
  `unknown`. v2: retorno `{resolved, excluded, unknown}` — paridad exigida sobre
  `resolved`/`unknown`; `excluded` es derivado UI-only (documentado).
- **C11 (MENOR, resuelto):** faltaba el caso borde `mode="todo"` con catálogo VACÍO
  (solo estaba el de selection sin matches). v2: +1 test F1.
- **C12 (MENOR, resuelto):** el checklist F6 v1 decía "grep de este plan no introduce
  ningún literal `stages:` fuera de tests" (vago: `"stages"` como key de dict SÍ
  aparece legítimamente). v2: criterio binario real — `publication_spec.py` con 0
  ocurrencias case-insensitive de `yaml` y sin importar `pipeline_renderers`.
- **C13 (MENOR, resuelto):** v2 declara explícitamente que este plan NO agrega campos
  al `PipelineSpec` ⇒ el centinela `test_f1_spec_shape_frozen` del 87 v2 y los tipos TS
  espejo (`specBuilder.ts`) quedan INTACTOS (si alguna evolución futura agregara
  campos, debe actualizar centinela + TS en el mismo commit, regla del 87 v2).
- **[ADICIÓN ARQUITECTO] Fixture COMPARTIDO de resolución py↔ts:** la paridad semántica
  entre `resolve_processes` (Python) y `resolvePreview` (TS) v1 dependía de COPIAR
  fixtures a mano en dos archivos (drift garantizado a la primera evolución). v2 crea
  UN solo archivo de datos `backend/tests/fixtures/plan88_resolution_cases.json`
  (catálogo + casos con esperado) que parametriza AMBOS lados: pytest
  (`test_f1_shared_fixture_cases`) y vitest (`resolvePreview_shared_fixture_parity`).
  La paridad pasa a ser por DATOS, no por disciplina. Beneficia también al plan 89
  (compone el preset TODO sobre esta misma semántica congelada).

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

**KPI / impacto esperado** (aspiracional; los criterios binarios están en F6):
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
   (mecanismo DECLARATIVO del plan 82, `harness_flags.py:30` — informa la relación en
   la UI; el guard runtime de cada endpoint chequea SU propia flag, patrón del repo),
   categoría `devops` (creada por plan 87 F0), `env_only=False` ⇒ **alta obligatoria
   en `config.py`** (gotcha plan 81), **SIN `default=` explícito** (gotcha
   `_CURATED_DEFAULTS_ON`), **CON `label` y `group`** (campos requeridos del dataclass,
   C3), **con entrada `PlainHelp`** en `services/harness_flags_help.py` (meta-test plan
   86), **y con su línea en `backend/harness_defaults.env`** (pata de deploy, C8).
4. **Byte-idéntico con flag OFF:** endpoints nuevos 404, sección UI ausente,
   validaciones aditivas inertes (key ausente = no-op).
5. **No degradar:** contratos de 45/71/72/73/87 intactos; todo aditivo. Este plan NO
   agrega campos a `PipelineSpec` ⇒ `test_f1_spec_shape_frozen` (87 v2) y
   `specBuilder.ts` NO se tocan (C13).
6. **3 runtimes (Codex/Claude/Copilot):** no toca el camino de agentes; impacto
   NINGUNO en los tres. Se declara por fase.
7. **Ratchet:** tests backend nuevos registrados en `backend/scripts/run_harness_tests.sh`
   y `.ps1`.
8. **Dominio, no hardcode:** los NOMBRES de procesos (Mul2Bane, IncHost, RSCore,
   RsExtrae) NUNCA se hardcodean en código de producción; viven en el process_catalog
   del client_profile. El código solo conoce `kind` y `publish_group`.
9. **NUNCA PUTear un client_profile parcial (C2 — riel §3.10 del 87 v2):**
   `put_client_profile` REEMPLAZA el profile completo (`api/client_profile.py:161`).
   TODO guardado desde la UI de este plan (presets, settings, publish_group) hace
   **GET del profile actual → merge en memoria (`mergeKeysIntoProfile`, F4) → PUT del
   profile completo**. Prohibido enviar `{"devops_publication_presets": [...]}` solo:
   borraría `process_catalog` y el resto de la config del operador.

## 4. Modelo de datos (contrato, consumido por F1-F5)

Todo persiste en el client_profile del proyecto (patrón plan 45), bajo keys NUEVAS:

```json
"devops_publication_presets": [
  {
    "name": "quincena-batch",
    "mode": "selection",                    // "selection" | "todo"
    "process_names": ["Mul2Bane", "IncHost"],  // SOLO mode=selection; orden irrelevante (manda el catálogo)
    "groups": ["batch"],                     // filtro opcional: subset de {"batch","agenda"}; [] o ausente = sin filtro
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

Límites de presets (C4, coherente con 87 v2 C7): máximo **50** presets; `name`
obligatorio, **único** dentro de la lista y de **≤120** caracteres.

Y un campo NUEVO OPCIONAL por entrada del process_catalog existente:
`"publish_group": "batch" | "agenda"` (ausente = sin grupo; se tolera, plan 45 tolera
borradores). "Batch" y "agenda" son GRUPOS DE PUBLICACIÓN, NO el `kind` existente
(`entry/processing/output`, `client_profile.py:57`): un proceso tiene un kind (rol en
el flujo de datos) Y opcionalmente un grupo (cadencia de publicación).

**Semántica de resolución (F1, determinista):**
- Entradas del catálogo que NO sean dict, o sin `name` string no vacío, se IGNORAN
  silenciosamente (C5, robustez ante catálogo editado a mano).
- `mode="todo"` ⇒ candidatos = TODAS las entradas válidas del catálogo.
  `mode="selection"` ⇒ candidatos = entradas cuyo `name` ∈ `process_names`
  (case-sensitive; los names no encontrados se reportan en `unknown_processes`, NO
  abortan).
- Filtro `groups`: si `groups` no vacío ⇒ quedan solo candidatos con
  `publish_group` ∈ `groups`. Si `groups == []` o la key está AUSENTE ⇒ sin filtro
  (entra todo, con o sin grupo).
- Orden del pipeline: stages por kind en orden canónico del flujo de carga
  **entry → processing → output** (Mul2Bane→IncHost/RSCore→RsExtrae); dentro de cada
  stage, un job por proceso preservando el ORDEN DEL CATÁLOGO. Kind ausente/desconocido
  ⇒ stage final `otros`.
- Script del step: `step_templates[kind]` si existe, sino `step_templates["default"]`,
  sino el literal `echo "[stacky] publicar {process_name}"`. Sustitución: SOLO el
  placeholder `{process_name}` (reemplazo de string simple, NO `str.format` — evita
  KeyError con llaves en comandos reales).
- El dict spec resultante SOLO usa keys ya congeladas por `test_f1_spec_shape_frozen`
  (87 v2): `name`, `stages[].name`, `stages[].jobs[].name`,
  `stages[].jobs[].steps[].{name,script}`. CERO campos nuevos (C13).

**Fixture compartido de resolución ([ADICIÓN ARQUITECTO], creado en F1):**
`Stacky Agents/backend/tests/fixtures/plan88_resolution_cases.json` — contenido
literal:

```json
{
  "catalog": [
    {"name": "Mul2Bane", "kind": "entry",      "publish_group": "batch"},
    {"name": "IncHost",  "kind": "processing", "publish_group": "batch"},
    {"name": "RSCore",   "kind": "processing", "publish_group": "batch"},
    {"name": "RsExtrae", "kind": "output",     "publish_group": "batch"},
    {"name": "AgendaX",  "kind": "processing", "publish_group": "agenda"},
    {"name": "SinGrupo", "kind": "output"}
  ],
  "cases": [
    {"id": "todo_all",        "preset": {"name": "t", "mode": "todo", "groups": []},
     "resolved": ["Mul2Bane", "IncHost", "RSCore", "RsExtrae", "AgendaX", "SinGrupo"], "unknown": []},
    {"id": "todo_batch",      "preset": {"name": "t", "mode": "todo", "groups": ["batch"]},
     "resolved": ["Mul2Bane", "IncHost", "RSCore", "RsExtrae"], "unknown": []},
    {"id": "todo_agenda",     "preset": {"name": "t", "mode": "todo", "groups": ["agenda"]},
     "resolved": ["AgendaX"], "unknown": []},
    {"id": "selection_mixed", "preset": {"name": "t", "mode": "selection", "process_names": ["RSCore", "NoExiste", "Mul2Bane"], "groups": []},
     "resolved": ["Mul2Bane", "RSCore"], "unknown": ["NoExiste"]},
    {"id": "selection_none",  "preset": {"name": "t", "mode": "selection", "process_names": ["Nada"], "groups": []},
     "resolved": [], "unknown": ["Nada"]}
  ]
}
```

Lo consumen pytest (F1) y vitest (F4). Si la semántica evoluciona, se toca UN archivo
y ambos lados fallan juntos (paridad por datos).

## 5. Fases

> Comandos de test (C9): backend = pytest POR ARCHIVO con
> `backend/.venv/Scripts/python.exe` ejecutado desde `Stacky Agents/backend`
> (87 v2 §4 preámbulo — la suite completa está contaminada). Frontend =
> `npx tsc --noEmit` + `npx vitest run <archivo>` en `Stacky Agents/frontend`; vitest
> queda instalado como devDependency por el **87 v2 F3.0** — NO re-instalarlo, y NUNCA
> correr `npx vitest run` sin archivo (colectaría los `.tsx` huérfanos de
> `src/components/__tests__/` que importan `@testing-library/react` inexistente).

### F0 — Flag `STACKY_DEVOPS_PUBLICATIONS_ENABLED`

**Objetivo:** alta correcta de la flag en las 4 patas + la pata de deploy (C8),
colgada de la del panel.

**Archivos a editar (mismos del plan 87 v2 F0, misma mecánica, + harness_defaults.env):**
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
   - `FlagSpec` nuevo junto al del plan 87. Snippet COMPLETO (C3: `label` y `group`
     son campos REQUERIDOS del dataclass, `harness_flags.py:21-33`):
     ```python
     FlagSpec(
         key="STACKY_DEVOPS_PUBLICATIONS_ENABLED",
         type="bool",
         label="Publicaciones DevOps (Plan 88)",
         description=(
             "Plan 88 — Seccion Publicaciones del panel DevOps: materializa presets "
             "de procesos del catalogo como pipelines (preview/commit plan 73, "
             "trigger plan 72). Default OFF. Con OFF el endpoint materialize da 404 "
             "y la seccion no aparece."
         ),
         group="global",  # mismo group que STACKY_DEVOPS_PANEL_ENABLED (87 v2 F0)
         env_only=False,  # editable por UI (categoría 'devops')
         requires="STACKY_DEVOPS_PANEL_ENABLED",  # Plan 82 — declarativo, informa en UI
     )
     ```
     ⚠️ SIN `default=`, SIN `reserved=` (consumidor real en F3).
3. `Stacky Agents/backend/services/harness_flags_help.py`: entrada `PlainHelp` para la
   key (modelo: la de `STACKY_PIPELINE_GENERATOR_ENABLED`, línea 595).
4. **(C8)** `Stacky Agents/backend/harness_defaults.env`: agregar la línea
   `STACKY_DEVOPS_PUBLICATIONS_ENABLED=false` (pata de deploy: el snapshot se hornea
   en `backend\.env` en cada release). Nota: si al implementar se detecta que la flag
   del 87 (`STACKY_DEVOPS_PANEL_ENABLED`) tampoco tiene su línea, agregarla en el
   mismo commit (1 línea; el 87 v2 no la incluyó y es la misma causa raíz que obligó
   fixes post-hoc en los planes 74/75).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_publications_flag.py`:
- `test_f0_flag_in_registry`: key en `FLAG_REGISTRY`, `env_only is False`,
  `requires == "STACKY_DEVOPS_PANEL_ENABLED"`, `group == "global"`, `label` no vacío.
- `test_f0_flag_in_category_devops`: key en `_CATEGORY_KEYS["devops"]`.
- `test_f0_config_default_off` (patrón inmune al env del runner, 87 v2 C8):
  `monkeypatch.delenv("STACKY_DEVOPS_PUBLICATIONS_ENABLED", raising=False)` +
  `importlib.reload(config)` + assert `config.config.STACKY_DEVOPS_PUBLICATIONS_ENABLED is False`.
- `test_f0_flag_has_plain_help`: key presente en el dict de `harness_flags_help.py`.
- `test_f0_harness_defaults_contains_flag` (C8): `backend/harness_defaults.env`
  existe y contiene el literal `STACKY_DEVOPS_PUBLICATIONS_ENABLED=false` (copiar el
  patrón de `tests/test_plan75_deep_links_wiring.py:50-58`).
- No-regresión: correr también `tests/test_harness_flags.py` y `tests/test_flag_wiring.py`.

**Ratchet:** registrar el archivo en ambos scripts.
**Criterio binario:** 5 tests nuevos + 2 meta verdes; default OFF.
**Flag:** `STACKY_DEVOPS_PUBLICATIONS_ENABLED` (default OFF).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno (opt-in).

### F1 — Materializador PURO `services/publication_spec.py` (corazón del plan)

**Objetivo:** función pura y determinista `preset + catálogo (+ settings) → dict
PipelineSpec` + fixture compartido de resolución (ADICIÓN).

**Archivo NUEVO (datos):** `Stacky Agents/backend/tests/fixtures/plan88_resolution_cases.json`
con el contenido LITERAL de §4 (crearlo ANTES de los tests; el directorio
`tests/fixtures/` ya existe — plan 74 dejó `tests/fixtures/migrator/`).

**Archivo NUEVO (código):** `Stacky Agents/backend/services/publication_spec.py`
```python
"""publication_spec.py — Plan 88. PURO: sin I/O, sin config, sin flags.
Convierte un preset de publicación + process_catalog en un dict PipelineSpec
(el mismo shape que consume dict_to_spec, services/pipeline_spec.py:69).
NO genera texto de pipeline: eso es exclusivo de pipeline_renderers (plan 73).
Prohibido importar pipeline_renderers acá (criterio binario F6)."""

_KIND_ORDER = ("entry", "processing", "output")   # flujo canónico de carga
_FALLBACK_STAGE = "otros"                          # kind ausente/desconocido
_DEFAULT_TEMPLATE = 'echo "[stacky] publicar {process_name}"'
_ALLOWED_GROUPS = ("batch", "agenda")

def resolve_processes(preset: dict, catalog: list[dict]) -> tuple[list[dict], list[str]]:
    """(procesos_resueltos_en_orden_de_catalogo, unknown_processes).
    mode='todo' -> todo el catálogo; mode='selection' -> por name (case-sensitive).
    Luego filtro groups (si no vacío, exige publish_group ∈ groups; ausente/[] = sin filtro).
    Entradas del catálogo que no sean dict, o sin 'name' string no vacío, se ignoran
    silenciosamente (C5)."""

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
    SOLO estas keys — cero campos nuevos en el spec (C13: test_f1_spec_shape_frozen
    del 87 v2 queda intacto).
    Sin procesos resueltos -> spec con stages=[] (inválido a propósito: _validate_spec
    lo rechaza aguas abajo; este módulo NO valida, igual que dict_to_spec)."""
```

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_publication_spec.py`.
Fixture local `_CATALOG` = el array `catalog` del JSON compartido (cargarlo del JSON,
no copiarlo):
```python
import json
from pathlib import Path

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "plan88_resolution_cases.json")
    .read_text(encoding="utf-8")
)
_CATALOG = _FIXTURE["catalog"]
```
- `test_f1_todo_includes_everything`: `mode="todo", groups=[]` ⇒ resolved = los 6, en
  orden de catálogo dentro de cada stage; stages = `["entry","processing","output"]`.
- `test_f1_todo_is_dynamic`: mismo preset, catálogo con 1 entrada más ⇒ resolved crece
  (criterio "TODO dinámico").
- `test_f1_todo_empty_catalog` (C11): `mode="todo"` con `catalog=[]` ⇒
  `resolved == []`, `unknown_processes == []`, `dict_to_spec(spec).validate()`
  devuelve errores (no explota).
- `test_f1_groups_filter_batch`: `mode="todo", groups=["batch"]` ⇒ resolved = 4
  (AgendaX y SinGrupo excluidos — SinGrupo no tiene publish_group).
- `test_f1_groups_filter_agenda`: `groups=["agenda"]` ⇒ solo AgendaX.
- `test_f1_groups_key_absent_no_filter`: preset SIN key `groups` ⇒ igual que `groups=[]`.
- `test_f1_selection_by_name_with_unknown`: `mode="selection",
  process_names=["RSCore","NoExiste","Mul2Bane"]` ⇒ resolved = ["Mul2Bane","RSCore"]
  (orden de CATÁLOGO, no del preset); `unknown_processes == ["NoExiste"]`.
- `test_f1_stage_order_canonical`: stages en orden entry→processing→output; job de
  Mul2Bane en stage "entry"; RsExtrae en "output".
- `test_f1_unknown_kind_goes_otros`: entrada con `kind="zzz"` ⇒ stage "otros" al final.
- `test_f1_non_dict_entries_ignored` (C5): catálogo con `["basura", 42, {...válida...}]`
  ⇒ solo la válida se resuelve; nada lanza.
- `test_f1_template_per_kind_and_placeholder`: settings con
  `step_templates={"entry": "deploy-entry {process_name} --now"}` ⇒ script del step de
  Mul2Bane == `"deploy-entry Mul2Bane --now"`; RSCore (sin template processing) usa
  `_DEFAULT_TEMPLATE` con el nombre sustituido.
- `test_f1_braces_in_template_safe`: template `"run {process_name} ${VAR} {otra}"` ⇒
  `{otra}` y `${VAR}` quedan LITERALES (prueba anti-str.format).
- `test_f1_spec_renders_via_plan73`: el spec resultante pasa por
  `dict_to_spec(result["spec"]).validate() == []` y `to_ado_yaml` + `to_gitlab_yaml`
  no lanzan (integración con el motor real, sin mocks; los imports de renderers viven
  en el TEST, jamás en `publication_spec.py`).
- `test_f1_pure_no_mutation`: el catálogo y el preset de entrada NO se mutan
  (comparar deepcopy previo).
- **[ADICIÓN]** `test_f1_shared_fixture_cases` (parametrizado):
  ```python
  import pytest

  @pytest.mark.parametrize("case", _FIXTURE["cases"], ids=[c["id"] for c in _FIXTURE["cases"]])
  def test_f1_shared_fixture_cases(case):
      resolved, unknown = resolve_processes(case["preset"], _FIXTURE["catalog"])
      assert [e["name"] for e in resolved] == case["resolved"]
      assert unknown == case["unknown"]
  ```

**Ratchet:** registrar el archivo.
**Criterio binario:** 15 tests nombrados verdes (14 + 1 parametrizado con 5 casos).
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
   keys nuevas (key ausente = no-op literal). Con límites C4 (mismo patrón que los
   drafts del 87 v2 C7):
   ```python
   # Plan 88 F2 — presets de publicación (aditivo; ausente = no-op).
   presets = profile.get("devops_publication_presets")
   if presets is not None:
       if not isinstance(presets, list):
           return jsonify({"ok": False, "error": "devops_publication_presets debe ser una lista."}), 400
       if len(presets) > 50:
           return jsonify({"ok": False, "error": "devops_publication_presets: maximo 50 presets."}), 400
       seen_names = set()
       for idx, p in enumerate(presets):
           if not isinstance(p, dict) or not isinstance(p.get("name"), str) or not p.get("name").strip():
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].name es obligatorio."}), 400
           name = p["name"].strip()
           if len(name) > 120:
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].name supera 120 caracteres."}), 400
           if name in seen_names:
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].name duplicado: '{name}'."}), 400
           seen_names.add(name)
           if p.get("mode") not in ("selection", "todo"):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].mode debe ser 'selection' o 'todo'."}), 400
           if p.get("mode") == "selection" and not isinstance(p.get("process_names"), list):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].process_names debe ser una lista en mode=selection."}), 400
           groups = p.get("groups", [])
           if not isinstance(groups, list) or any(g not in ALLOWED_PUBLISH_GROUPS for g in groups):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].groups: subset de {sorted(ALLOWED_PUBLISH_GROUPS)}."}), 400
           if p.get("target") not in (None, "ado", "gitlab"):
               return jsonify({"ok": False, "error": f"devops_publication_presets[{idx}].target debe ser 'ado' o 'gitlab'."}), 400
   # Plan 88 F2 — settings de publicación (aditivo; ausente = no-op).
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

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_presets_validation.py`
(mismo setup de PUT exitoso que el test de plan 87 F2):
- `test_f2_absent_keys_noop`: PUT sin las keys nuevas ⇒ 200.
- `test_f2_preset_bad_mode_400`, `test_f2_preset_no_name_400`,
  `test_f2_selection_without_names_400`, `test_f2_bad_group_400`,
  `test_f2_bad_target_400`.
- `test_f2_duplicate_preset_name_400` (C4): 2 presets con `name="a"` ⇒ 400.
- `test_f2_over_50_presets_400` (C4): 51 presets válidos ⇒ 400.
- `test_f2_preset_name_over_120_400` (C4): name de 121 chars ⇒ 400.
- `test_f2_publish_group_invalid_400`: catálogo con `publish_group="mensual"` ⇒ 400
  con `error == "invalid_publish_group"`.
- `test_f2_publish_group_absent_tolerated`: catálogo sin el campo ⇒ 200 (backward compat).
- `test_f2_valid_roundtrip`: PUT con presets+settings+publish_group válidos ⇒ 200 y el
  GET devuelve las 3 keys intactas.
- `test_f2_bad_template_key_400`: `step_templates={"deploy": "x"}` ⇒ 400.

**Ratchet:** registrar. **Criterio binario:** 13 tests verdes + tests existentes de
client_profile y los del plan 87 F2 verdes.
**Flag:** ninguna (aditivo inerte). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Endpoint `POST /api/devops/publications/materialize` (solo-lectura)

**Objetivo:** exponer el materializador con datos reales del proyecto; cero efectos.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py` (creado en plan 87 F1).
Imports nuevos arriba del archivo (VERIFICADOS, C7 — sin "grep antes de escribir"):
```python
from services.publication_spec import build_publication_spec
from services.client_profile import load_client_profile  # services/client_profile.py:266
```
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
    profile = load_client_profile(project) or {}
    # C5 — defensivo: el profile puede haberse editado por JSON directo.
    presets_raw = profile.get("devops_publication_presets")
    presets = [p for p in presets_raw if isinstance(p, dict)] if isinstance(presets_raw, list) else []
    preset = next((p for p in presets if p.get("name") == preset_name), None)
    if preset is None:
        return jsonify({"error": f"preset '{preset_name}' no existe", "kind": "preset_not_found"}), 404
    catalog = profile.get("process_catalog")
    settings = profile.get("devops_publication_settings")
    result = build_publication_spec(
        preset,
        catalog if isinstance(catalog, list) else [],
        settings if isinstance(settings, dict) else None,
    )
    return jsonify(result)   # {'spec':..., 'resolved':[...], 'unknown_processes':[...]}
```
Además, en `devops_health_route` (plan 87 F1), agregar al JSON:
`"publications_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False))`
(aditivo; el contrato del plan 87 no se rompe: solo se agrega una key — previsto por
el 87 v2 F4: "las keys nuevas del health viajan por ctx.health de forma aditiva").

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan88_materialize_endpoint.py`
(fixtures `app_flag_on`/`app_flag_off` sobre `STACKY_DEVOPS_PUBLICATIONS_ENABLED`,
patrón `test_plan73_generator_endpoint.py:8-31`). Mocks (C7):
- el LOADER se patchea donde se usa: `unittest.mock.patch("api.devops.load_client_profile", ...)`
  (patrón lazy-import del repo);
- el SAVER se patchea en su módulo de ORIGEN:
  `unittest.mock.patch("services.client_profile.save_client_profile")` —
  `api/devops.py` NO lo importa, patchearlo en `api.devops` daría AttributeError.
- `test_f3_flag_off_404`.
- `test_f3_missing_params_400`: sin `project` ⇒ 400; sin `preset_name` ⇒ 400.
- `test_f3_preset_not_found_404`: profile sin ese preset ⇒ 404 con
  `kind == "preset_not_found"`.
- `test_f3_materialize_ok`: profile mockeado con el `catalog` del fixture compartido +
  preset todo ⇒ 200, `resolved` == 6 names, `spec.name` empieza con `"publicacion-"`.
- `test_f3_corrupt_presets_no_500` (C5): profile con
  `devops_publication_presets = {"no": "lista"}` ⇒ 404 `preset_not_found` (nunca 500);
  ídem con lista que contiene strings sueltos.
- `test_f3_readonly_no_writes`: `services.client_profile.save_client_profile` mockeado
  NO fue llamado (`assert_not_called`) tras un materialize exitoso — materializar
  jamás escribe.
- `test_f3_health_exposes_publications_enabled`: GET `/api/devops/health` contiene la
  key `publications_enabled` (bool).

**Ratchet:** registrar. **Criterio binario:** 7 tests verdes + los del plan 87 F1 verdes.
**Flag:** `STACKY_DEVOPS_PUBLICATIONS_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: modelo puro de presets + merge de profile + API client

**Objetivo:** lógica de edición de presets pura y testeable; merge seguro del
client_profile (C2); llamadas tipadas.

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
  (mismas reglas que F2, para feedback inmediato en UI: name vacío o >120 chars, mode
  inválido, selection sin process_names, groups fuera de allowlist).
- **`mergeKeysIntoProfile(profile: object | null, patch: object): object` (C2):**
  función pura `{...(profile ?? {}), ...patch}` — copia superficial NUEVA, no muta el
  input, preserva TODAS las keys ajenas (`process_catalog`, drafts del 87, etc.). Es
  la ÚNICA vía por la que F5 construye el body del PUT (análoga a
  `mergeDraftsIntoProfile` del 87 v2 F3, pero genérica por keys — NO duplicar la del
  87: aquella es específica de drafts, ésta sirve para presets Y settings Y catálogo).
- `resolvePreview(preset, catalog): {resolved: string[]; excluded: string[]; unknown: string[]}`
  (C10) — semántica de `resolve_processes` de F1 sobre `resolved`/`unknown` (paridad
  verificada contra el fixture compartido); `excluded` (candidatos que el filtro de
  groups dejó fuera) es DERIVADO UI-ONLY, el backend no lo computa. La fuente de
  verdad sigue siendo el backend: el spec siempre viene del endpoint.

**Archivo a editar:** `Stacky Agents/frontend/src/api/endpoints.ts` — extender el
namespace `DevOps` del plan 87 v2 F3 (helper real `api.post` con path COMPLETO
`/api/...`, C6):
```ts
materializePublication: (project: string, presetName: string) =>
  api.post<{ spec: object; resolved: string[]; unknown_processes: string[] }>(
    "/api/devops/publications/materialize",
    { project, preset_name: presetName },
  ),
```

**Tests PRIMERO** — `Stacky Agents/frontend/src/devops/presetsModel.test.ts` (vitest
TS puro, sin React). El fixture compartido se lee del backend (UN solo archivo,
ADICIÓN):
```ts
import { readFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync(
    new URL("../../../backend/tests/fixtures/plan88_resolution_cases.json", import.meta.url),
    "utf-8",
  ),
);
```
- `upsert_replaces_by_name_immutable`; `remove_absent_noop`;
- `validate_selection_without_names_fails`; `validate_todo_ok`;
- **[ADICIÓN]** `resolvePreview_shared_fixture_parity`: para CADA `case` de
  `fixture.cases`, `resolvePreview(case.preset, fixture.catalog)` cumple
  `resolved` deep-equal `case.resolved` y `unknown` deep-equal `case.unknown`
  (paridad por datos con `test_f1_shared_fixture_cases` — mismo archivo fuente).
- `mergeKeys_preserves_foreign_keys` (C2): dado
  `profile = {process_catalog: [{kind: "entry"}], otra_key: 1}`,
  `mergeKeysIntoProfile(profile, {devops_publication_presets: [p]})` devuelve un
  objeto NUEVO con `process_catalog` y `otra_key` INTACTOS + la key nueva, y el input
  no mutó.
- `mergeKeys_null_profile` (C2): `mergeKeysIntoProfile(null, {devops_publication_presets: []})`
  ⇒ `{devops_publication_presets: []}` (proyecto sin client_profile).

Comando: `npx vitest run src/devops/presetsModel.test.ts`.
**Criterio binario:** vitest verde (7 tests nombrados; el de paridad itera 5 casos) +
`npx tsc --noEmit` 0 errores.
**Flag:** ninguna (código sin montar hasta F5).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F5 — Frontend: sección "Publicaciones" en el panel DevOps

**Objetivo:** UI completa del flujo preset → materializar → preview YAML → commit
HITL → trigger HITL, montada como sección del plan 87 v2.

**Archivos NUEVOS** (en `Stacky Agents/frontend/src/components/devops/`):
1. `PublicationsSection.tsx` — recibe `ctx: DevOpsSectionContext` (contrato 87 v2 F4;
   C1). Layout 2 columnas:
   - Izquierda: lista de presets (leída de `devops_publication_presets` vía
     `GET /api/projects/<name>/client-profile`, ruta `client_profile.py:93` — igual
     que los drafts del plan 87 F5), botones crear/editar/borrar (usa
     `presetsModel.ts`), editor de preset: nombre; radio mode (selection/todo);
     checklist de procesos del `process_catalog` (solo mode=selection); checkboxes de
     grupos batch/agenda; select target. Debajo, editor de `step_templates` (4
     textareas etiquetadas entry/processing/output/default con hint del placeholder
     `{process_name}`).
     **Flujo de guardado (C2 — read-modify-write OBLIGATORIO, riel §3.9):**
     1. GET fresco del profile; `base = json.profile ?? {}`.
     2. `merged = mergeKeysIntoProfile(base, { devops_publication_presets: nuevosPresets })`
        (o `{ devops_publication_settings: ... }`, o `{ process_catalog: ... }` con el
        publish_group editado — SIEMPRE la key COMPLETA en el patch).
     3. `PUT /api/projects/<name>/client-profile` con body `{ profile: merged }`
        (el endpoint acepta el wrapper, `client_profile.py:132-133`).
     PROHIBIDO PUTear solo las keys nuevas: el PUT REEMPLAZA el profile completo
     (`client_profile.py:161`) y borraría `process_catalog` y el resto.
     Si el PUT devuelve 400 (validación F2), mostrar el `error` literal del backend.
   - Derecha: "Vista previa de resolución" en vivo (`resolvePreview`: entra `resolved`,
     sale `excluded`, warning con `unknown`); botón **"Materializar"** ⇒
     `DevOps.materializePublication` ⇒ muestra `resolved`/`unknown_processes` y pasa
     el `spec` recibido a los componentes REUSADOS del plan 87 F5:
     `PipelineYamlPreview` (preview ADO+GitLab vía `/api/pipeline-generator/preview`),
     `CommitPipelineModal` (HITL checkbox ⇒ `confirm:true`) y
     `TriggerPipelineSection` (HITL plan 72; visible solo si
     `ctx.health.trigger_enabled === true`). Si `unknown_processes` no vacío ⇒ warning
     visible listándolos.
   - Si `ctx.health.publications_enabled !== true` ⇒ la sección entera se reemplaza
     por el mensaje "Activá STACKY_DEVOPS_PUBLICATIONS_ENABLED (Configuración → Arnés,
     categoría DevOps)" (patrón MigratorPage.tsx:35-47).
2. Además: en la checklist de procesos y el editor del catálogo YA existente del plan
   45 (buscar el componente que edita `process_catalog` en
   `frontend/src/components/` — grep `process_catalog` — y SOLO SI existe un editor de
   entradas), agregar el select opcional `publish_group` (vacío/batch/agenda); su
   guardado usa el MISMO flujo GET→merge→PUT de arriba. Si no existe editor de
   entradas, NO crearlo: el publish_group se edita vía el JSON del client_profile como
   hasta ahora, y la sección Publicaciones muestra el grupo como badge de solo
   lectura. (Decisión binaria verificable: existe editor ⇒ select; no existe ⇒ badge.)

**Archivos a editar:**
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — agregar a `DEVOPS_SECTIONS`
  (punto de extensión del plan 87 v2 F4, firma `render(ctx)` — C1):
  ```ts
  { id: "publicaciones", label: "Publicaciones", render: (ctx) => <PublicationsSection ctx={ctx} /> },
  ```
  y ampliar ADITIVAMENTE la interfaz `DevOpsHealth` (definida en DevOpsPage.tsx, 87 v2
  F4) con la key OPCIONAL:
  ```ts
  publications_enabled?: boolean;
  ```
  (opcional para no romper el fixture/uso del 87; el backend ya la envía desde F3).

**Tests:** lógica cubierta en F4 (vitest). Gate componentes = `npx tsc --noEmit`.
**Criterio binario:** `tsc` 0 errores; la sección solo es visible con AMBAS flags ON;
commit/trigger inaccesibles sin confirmación explícita (checkbox/preview HITL —
verificable por código); todo PUT de client-profile del plan pasa por
`mergeKeysIntoProfile` (verificable: grep de `client-profile` en
`PublicationsSection.tsx` — ninguna llamada PUT construye el body sin el helper).
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
npx vitest run src/devops/presetsModel.test.ts
npx vitest run src/devops/specBuilder.test.ts
npx tsc --noEmit
```

**Checklist binario de done:**
- [ ] Flag OFF ⇒ `/api/devops/publications/materialize` 404, sección UI ausente,
      byte-idéntico (no-regresión verde).
- [ ] Preset "TODO" con catálogo de 6 ⇒ pipeline de 3 stages en orden
      entry→processing→output; agrego una entrada al catálogo y re-materializo ⇒ la
      nueva entrada aparece SIN tocar el preset.
- [ ] Preset "solo agenda" excluye los batch (y viceversa).
- [ ] Cero YAML a mano (C12, binario): grep case-insensitive de `yaml` en
      `backend/services/publication_spec.py` ⇒ 0 ocurrencias, y el archivo NO importa
      `pipeline_renderers` (el YAML solo sale de `to_ado_yaml`/`to_gitlab_yaml` vía
      los endpoints del plan 73).
- [ ] Commit imposible sin checkbox HITL; trigger solo vía flujo HITL plan 72.
- [ ] Guardar presets/settings/publish_group NO pierde ninguna key ajena del
      client_profile (`mergeKeys_preserves_foreign_keys` verde + flujo F5
      read-modify-write) (C2).
- [ ] `test_f1_shared_fixture_cases` (pytest) y `resolvePreview_shared_fixture_parity`
      (vitest) verdes leyendo el MISMO archivo JSON (paridad por datos).
- [ ] `test_f1_spec_shape_frozen` (87 v2) sigue verde SIN modificaciones (C13).
- [ ] Archivos de test registrados en ambos scripts de ratchet.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| **PUT de client_profile REEMPLAZA el profile ⇒ guardar presets podría borrar config del operador (C2)** | Riel §3.9 + flujo F5 read-modify-write literal + helper puro `mergeKeysIntoProfile` + tests `mergeKeys_*` |
| Presets corruptos (JSON editado a mano) ⇒ 500 en materialize (C5) | Filtro defensivo `isinstance` en el endpoint + entradas no-dict ignoradas en el módulo puro + `test_f3_corrupt_presets_no_500` |
| Confundir `kind` (entry/processing/output) con grupo batch/agenda | Campo NUEVO `publish_group` ortogonal + glosario + tests F1/F2 que usan ambos a la vez |
| `str.format` sobre templates con `{}` de shell | Prohibido por contrato (§4) + `test_f1_braces_in_template_safe` |
| Drift semántico entre `resolve_processes` (py) y `resolvePreview` (ts) | **Fixture COMPARTIDO único** (`plan88_resolution_cases.json`) parametriza ambos lados (ADICIÓN); backend = fuente de verdad (el spec siempre viene del endpoint) |
| Hardcodear procesos Pacífico en producción | Prohibido (§3.8); solo aparecen en el fixture de test |
| PUT client_profile crece en validaciones y se vuelve frágil | Cada bloque es aditivo, key ausente = no-op, con test explícito de no-op |
| Preset apunta a procesos borrados del catálogo | `unknown_processes` reportado (nunca aborta) + warning en UI |
| Preset duplicado ⇒ selector ambiguo | Unicidad + cap 50 + ≤120 chars validados en F2 (C4, mismo patrón drafts 87 v2 C7) |
| Flag 88 ON con flag 87 OFF (env directo) | `requires` es declarativo (plan 82): la sección UI no existe sin el panel; el endpoint materialize sigue siendo SOLO-LECTURA y commit/trigger conservan sus propios guards (73/72) — sin efecto colateral posible |
| Plan 87 no implementado aún | Dependencia declarada arriba (87 **v2**); F0-F2 de este plan no dependen de código del 87 (solo F3 toca `api/devops.py` y F5 la página) — orden de implementación lo respeta |

## 7. Fuera de scope (v1)

- Ejecutar la publicación DIRECTO sobre servidores (esto genera/commitea/dispara
  pipelines; el deploy real lo hace el pipeline en el runner de CI).
- Scheduling/cron de publicaciones (violaría HITL; el trigger es siempre manual).
- Grupos de publicación adicionales a batch/agenda (allowlist cerrada v1).
- Plantillas de step por PROCESO individual (v1 es por kind; el escape hatch es editar
  el pipeline resultante en el builder del plan 87).
- Inicialización de ambientes ⇒ plan 3 de la serie (plan 89, dependerá de éste).

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
- **Fixture compartido de resolución**: `backend/tests/fixtures/plan88_resolution_cases.json`
  — único archivo de datos que congela la semántica de resolución para pytest Y vitest.
- **mergeKeysIntoProfile**: helper puro TS que mezcla un patch de keys sobre el profile
  completo antes del PUT (el PUT reemplaza TODO el documento, riel §3.9).
- **process_catalog / client_profile / HITL / FLAG_REGISTRY / ratchet /
  DevOpsSectionContext**: ver glosario del plan 87 v2 §7.
- **Flujo canónico Pacífico**: Mul2Bane (entry, deja en IN_) → IncHost (→productivas)
  → RSCore (aplica) → RsExtrae (salida); es el ORIGEN del orden entry→processing→output.

## 9. Orden de implementación

1. F0 — flag (4 patas + harness_defaults.env; tests meta verdes).
2. F1 — fixture compartido + `services/publication_spec.py` puro (15 tests).
3. F2 — validación aditiva client_profile (13 tests).
4. F3 — endpoint materialize + health key (requiere plan 87 F1 implementado).
5. F4 — `presetsModel.ts` (incl. `mergeKeysIntoProfile`) + endpoints.ts (vitest).
6. F5 — `PublicationsSection` + registro `render(ctx)` en `DEVOPS_SECTIONS` +
   `DevOpsHealth` ampliada (requiere plan 87 F4/F5).
7. F6 — cierre.

## 10. Definición de Hecho (DoD)

- 40 tests backend nombrados (F0:5, F1:15, F2:13, F3:7) verdes por archivo con el venv.
- Vitest F4 verde (7 tests, incl. paridad por fixture compartido);
  `npx tsc --noEmit` 0 errores.
- No-regresión: tests planes 87/73 + meta-tests del arnés verdes;
  `test_f1_spec_shape_frozen` intacto (C13).
- Flag OFF ⇒ byte-idéntico; checklist F6 completo.
- Cero YAML generado a mano (criterio binario C12); cero nombres de procesos
  hardcodeados en producción; ningún PUT parcial de client_profile (C2).
