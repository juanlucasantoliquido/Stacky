# Plan 266 — Catálogo único de acciones DevOps: una sola declaración, tres superficies, un solo contrato de confirmación

**Estado:** PROPUESTO v1 (2026-07-27) · **Autor:** pipeline proponer-plan-stacky · **Juez:** pendiente (criticar-y-mejorar-plan)

---

## 1. Objetivo

Hoy el panel DevOps tiene 17 secciones y decenas de acciones, y **cada acción existe una sola vez: pegada a mano en el JSX de la sección que la inventó**. No hay ninguna lista de "qué se puede hacer en DevOps". Por eso la paleta global no puede ejecutar ni una sola acción del panel (solo navega), el agente DevOps devuelve prosa en vez de una acción tipada, y cada sección se escribe su propia confirmación con su propio texto y su propio criterio de peligro. El plan 266 crea el **Catálogo de Acciones DevOps**: una declaración única y verificable de cada acción (qué es, en qué sección vive, si lee o escribe, qué impacto tiene, sobre qué entorno actúa, qué parámetros necesita, qué flag la gatea y cómo se pide en español), consumida por **las tres superficies**: los botones manuales que ya existen, la paleta de comandos, y el agente de lenguaje natural — que deja de contestar texto y pasa a devolver una **propuesta de acción tipada** (`ActionProposal`) con el molde de `IntentBrief` del plan 41: *qué acción, sobre qué entorno, qué impacto, qué va a pasar* → tarjeta de vista previa → `confirmGateway` → **recibo del resultado**. Un ratchet impide que nazca una acción nueva fuera del catálogo. Eso es lo que vuelve la coherencia de la UX **verificable por test** en vez de una promesa de checklist visual.

## 2. KPI / impacto (Antes medido contra el árbol del 2026-07-27)

| # | Métrica | Antes (medido) | Después (binario) | Comando que lo mide |
|---|---------|----------------|-------------------|---------------------|
| KPI-1 | Acciones del panel DevOps declaradas en un catálogo | **0** (no existe el archivo) | **≥ 23**, todas con `effect`+`impact`+`section_id`+`flag_key` | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_catalog.py -v` |
| KPI-2 | Comandos de la paleta que **ejecutan** una acción del panel | **0** — `NAV_COMMANDS` (`frontend/src/components/commandPaletteData.ts:59-76`) tiene 14 entradas y las 14 son navegación | **≥ 12** entradas `kind:"devops-action"` | `npx vitest run src/components/__tests__/commandPaletteDevopsActions.test.ts` |
| KPI-3 | Entidades cubiertas por el registro de acciones | **2** — `EntityKind = Extract<CommandKind,"execution"\|"ticket">` (`frontend/src/services/entityActions.ts:15`) | **3** (se suma `devops-action` como tercer vocabulario, sin tocar los 2 existentes) | `npx vitest run src/services/entityActions.test.ts src/services/devopsActionRunner.test.ts` |
| KPI-4 | Respuestas del agente DevOps que son una acción tipada | **0** — `api/devops_agent.py` lanza un turno de CLI y devuelve prosa (`backend/api/devops_agent.py:136-140`) | **100 %** de las frases que superan el umbral del matcher devuelven `ActionProposal` con `action_id` | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v` |
| KPI-5 | Runtimes soportados por el camino "lenguaje natural → acción" | **2 de 3** — `_CLI_RUNTIMES = ("claude_code_cli","codex_cli")` (`backend/api/devops_agent.py:14`) y Copilot recibe **400** `devops_chat_requires_cli_runtime` (`backend/api/devops_agent.py:69-78`) | **3 de 3**: el matcher determinista no usa modelo, así que Copilot obtiene propuesta y vista previa completas | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -k copilot -v` |
| KPI-6 | Confirmaciones de acciones DevOps construidas a mano fuera de `confirmGateway` | **≥ 6 archivos** (`BuildWorkshopSection.tsx`, `PipelineBuilderSection.tsx`, `ProductionFlow.tsx`, `RemoteConsoleSection.tsx`, `ServersSection.tsx`, `SolutionPublisherSection.tsx`) | **0 nuevas**: el ratchet prohíbe que aparezca una acción con efecto que no derive su `ConfirmRequest` del catálogo | `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts` |
| KPI-7 | Deriva backend↔frontend de acciones | **N/A** (no hay contrato que derive) | **0**: igualdad exacta de conjuntos entre ids del catálogo y claves de `DEVOPS_ACTION_BINDINGS` | `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts` |
| KPI-8 | Acciones con `effect:"write"` sin declarar impacto ni entorno | **N/A** | **0**: `targets_environment=True` ⇒ param `environment` obligatorio; `effect="write"` ⇒ `impact != "none"` | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v` |

Cómo se obtuvo cada "Antes": KPI-1 por ausencia del archivo (`backend/services/devops_action_catalog.py` no existe); KPI-2 contando las entradas del array literal en `commandPaletteData.ts:59-76` (el comentario de `:58` dice "13 tabs" — quedó desactualizado, hay 14); KPI-3 leyendo `entityActions.ts:15`; KPI-4 y KPI-5 leyendo `api/devops_agent.py`; KPI-6 por censo de `askConfirm`/modales propios en `frontend/src/components/devops/`.

---

## 3. Por qué ahora, y por qué esto NO duplica al plan 239

### 3.1 El 239 ya hizo el rediseño de shell. El 266 no lo toca.

`docs/239_PLAN_COCKPIT_DEVOPS_REDISENO_INTEGRAL_UX_UI_E_INFORMACION.md` está **IMPLEMENTADO (2026-07-25, F0..F8)** y entregó exactamente la parte estructural del rediseño:

- **F4** — shell v3 con navegación agrupada de dos niveles: `frontend/src/pages/devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, `DevOpsTabsV2.tsx`, `DevOpsHeaderV2.tsx`. Los 4 grupos están congelados en `devopsCockpitShell.ts:20-25` (`resumen` / `operar` / `construir` / `diagnosticar`).
- **F5** — deep-link `/devops/<seccion>` y sección de inicio fijable (`resolveLandingSection`, `devopsCockpitShell.ts:119-149`).
- **F6** — fin del sondeo perpetuo: `visible?: boolean` en el contexto (`DevOpsPage.tsx:76-79`) + ratchet `devopsPollingRatchet.test.ts`.
- **F7a** — convergencia a tokens: 0 hex en los `.module.css` de DevOps. **F7b** — barrido de estilos inline: 385 ≤ 386.
- **F1/F3** — sección Resumen (`backend/services/devops_overview.py`, `GET /api/devops/overview`, `DevOpsOverviewSection.tsx`).

Y declara textualmente que **falta solo lo VISUAL** (checklist de 10 puntos de F8 que requiere navegador; RTL y jsdom no están en el `package.json` del frontend).

**Conclusión operativa: re-proponer navegación, grupos, tokens o barrido de inline styles sería trabajo ya hecho.** El 266 hereda ese shell tal cual y no edita `devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, `DevOpsTabsV2.tsx` ni `DevOpsHeaderV2.tsx` (ver §8, frontera de merge). Lo único que el 266 agrega al shell es *consumir* `DevOpsSection.id`, que ya existe.

### 3.2 El gap que el 239 dejó abierto es de **acciones**, no de layout

El 239 unificó *dónde está cada cosa*. No unificó *qué se puede hacer y cómo se pide permiso*. Cuatro piezas del repo lo gritan:

1. **`frontend/src/services/entityActions.ts` (193 líneas, plan 175 F1)** ya demostró el patrón correcto: el registro es DATOS, no JSX. Su comentario de cabecera (`:3-5`) dice literalmente:
   > *"el menú contextual, las acciones rápidas inline y **(mañana) la paleta** consumen la misma lista. Si cada superficie armara la suya, terminarían ofreciendo cosas distintas para la misma entidad."*

   Ese "mañana" nunca llegó, y el registro cubre **2 entidades**: `EntityKind = Extract<CommandKind, "execution" | "ticket">` (`:15`). **Ninguna acción del panel DevOps está adentro.** Tiene el doble cerrojo `quickActions()` (`:44-46`: `a.quick && a.effect === "safe"`) — la semántica de seguridad correcta, aplicada a 2 de las ~23 acciones que el operador realmente ejecuta.

2. **`frontend/src/services/confirmGateway.ts`** ya es el punto único de HITL: `ConfirmRequest{title,message,confirmLabel,tone}` (`:10-15`), `ConfirmFn` (`:17`) y `denyByDefault` que **niega por default** (`:19-21`), con la prohibición explícita de diálogos nativos del navegador (`:7-8`). Pero como las acciones DevOps no están declaradas, cada sección arma su `ConfirmRequest` a mano con su propio criterio de `tone` — al menos 6 archivos (KPI-6).

3. **`frontend/src/components/commandPaletteData.ts` (125 líneas, plan 129)** tiene `Command{id,kind,icon,label,hint,run}` (`:21-28`), `CommandKind` con 9 valores (`:10-19`) y `fuzzyScore()` (`:31-49`) — toda la maquinaria para ejecutar acciones. Y `NAV_COMMANDS` (`:59-76`) son **14 entradas de navegación pura**. La paleta es un ascensor, no un panel de mandos.

4. **`backend/api/devops_agent.py` (364 líneas, plan 90)** es un chat de texto libre: `POST /devops/agent/conversations` con `project`/`message`/`runtime`/`model`/`server_alias`. No conoce ningún catálogo, no propone una acción tipada, no tiene contrato preview→confirmación→resultado. Además **rechaza Copilot con 400** (`:69-78`) y duplica el literal de efforts en `:15` (`_EFFORTS`), cuando el 264 congela ese eje en `services/model_catalog.py` + `services/llm_router.py`.

Y ya existe el molde exacto para el "esto entendí y así lo haría": **`backend/services/intent_preflight.py` (plan 41)** con `IntentBrief{objective,deliverables,assumptions,open_questions,areas,confidence,version}` (`:39-47`), `IntentAssumption{text,impact,needs_confirmation,basis}` (`:29-37`), `PreflightRuntimeUnavailable` (`:25-26`) y un parser tolerante `from_model_json` (`:81`). **No se inventa un contrato nuevo: se calca ese.**

### 3.3 Lo que pidió el operador, mapeado

| Pedido literal | Cómo lo cubre el 266 |
|---|---|
| "consultar el estado de los servicios" | acciones `devops.overview.refresh`, `devops.servers.list`, `devops.servers.doctor` (F7) |
| "gestionar despliegues" | `devops.deployments.history` (read) + `devops.deployment.execute` (write, `impact:high`) |
| "revisar logs" | `devops.logs.tail` (`section_id=None`, `nav_path="/logs"`) |
| "configurar pipelines" | `devops.pipelines.inventory`, `devops.pipeline_edit.preview` (read) + `devops.pipeline_edit.commit` (write) |
| "detectar incidencias" | `devops.incidents.list`, `devops.pipelines.audit` |
| "proponer soluciones" | `ActionProposal.what_will_happen` + `open_questions` + `alternatives` |
| "ejecutar acciones" | `runDevOpsAction()` — el **mismo** binding que usa el botón manual |
| "confirmar operaciones sensibles antes de realizarlas" | `confirmRequestFor()` derivado del catálogo → `confirmGateway`; `denyByDefault` |
| "mostrar qué acción, sobre qué entorno, cuál impacto, cuál resultado" | los 4 campos son **obligatorios** en la tarjeta: `label` / `environment` / `impact` / `DevOpsActionReceipt` |
| "sin eliminar la posibilidad de hacerlo manualmente" | los botones existentes **no se borran**: se recablean al mismo `runDevOpsAction` |

---

## 4. Principios y guardarraíles (aplican a todas las fases)

1. **Human-in-the-loop innegociable.** El agente **propone**, el operador **confirma**. Cero autonomía proactiva: ninguna fase agrega un loop, daemon, barrido, prefetch o inyección de contexto. Nada se ejecuta sin un click del operador. `denyByDefault` (`confirmGateway.ts:21`) es la semántica correcta y se reusa tal cual.
2. **Una sola declaración.** El catálogo backend es la fuente de verdad de la *identidad y la seguridad* de una acción. El binding frontend es la fuente de verdad de *cómo se hace*, reusando los endpoints que **ya existen**. Ningún endpoint de ejecución nuevo. Un ratchet exige igualdad de conjuntos entre ambos.
3. **Cero trabajo extra al operador.** Sin pasos manuales nuevos, sin configuración nueva, sin migración. Todas las acciones siguen disponibles con el mismo click de hoy.
4. **Regla de default de flags.** Toda flag nueva nace **ON**. Solo nace OFF si cae en **(A)** quema tokens en reposo o **(B)** escribe en un sistema real / le saca la decisión al operador. Leer, calcular, mostrar, diffear, auditar y avisar son **siempre ON**. Cuando una capacidad mezcla lo inocuo con lo que escribe, se **parte en dos flags** (precedente: `STACKY_PIPELINE_NL_EDIT_ENABLED` ON en `harness_flags.py:3149-3165` vs `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` OFF en `:3166-3187`).
5. **Paridad de 3 runtimes por construcción.** El matcher de intención es **determinista y sin modelo**. Codex CLI, Claude Code CLI y GitHub Copilot Pro obtienen el mismo catálogo, la misma propuesta y la misma vista previa. El enriquecimiento por LLM es un extra opcional que, si falla o no está disponible, **degrada al resultado determinista** — nunca a un error.
6. **Mono-operador.** Sin RBAC, sin roles, sin multiusuario. `current_user` sigue siendo el header sin validar de `api/_helpers.py`.
7. **Backward-compatible.** Con las tres flags apagadas, el panel DevOps queda **byte-idéntico** al de hoy. Ningún archivo existente cambia de comportamiento por default salvo el recableado de botones de F7, que preserva exactamente el mismo efecto y el mismo texto de confirmación.
8. **Reuso obligatorio.** `confirmGateway`, `entityActions` (patrón), `IntentBrief` (molde), `fuzzyScore` (paleta), `ModelEffortPicker` + `llm_router.clamp_model`/`clamp_effort_for_model` (264), flags del arnés, `devops_overview`. **Prohibido** crear un segundo mecanismo de confirmación, un segundo enum de efforts o un segundo catálogo de modelos.
9. **Nada de sondeo.** Ninguna fase introduce `setInterval`, `setTimeout` recurrente ni `refetchInterval`. `frontend/src/__tests__/devopsPollingRatchet.test.ts` (plan 239 F6) ya lo vigila y debe seguir verde.

### 4.1 Receta obligatoria de cableado de flags (7 patas)

Cada flag nueva de este plan toca **hasta 7 lugares**. Saltear uno deja un test en rojo:

| # | Lugar | Cuándo |
|---|---|---|
| 1 | `backend/config.py` — el atributo con `os.getenv(...)` | **siempre** (es el default EFECTIVO) |
| 2 | `backend/services/harness_flags.py` — la `FlagSpec` (campos en `:21-41`) | siempre |
| 3 | `backend/services/harness_flags.py` — `_CATEGORY_KEYS` (mapa en `:120`, categoría `"devops"` en `:223`) | siempre |
| 4 | `backend/services/harness_flags_help.py` — `PLAIN_HELP` (dict en `:25`, dataclass en `:17-23`) | siempre |
| 5 | `backend/tests/test_harness_flags.py:467` — `_CURATED_DEFAULTS_ON` | **solo si la `FlagSpec` declara `default=True`** |
| 6 | `backend/tests/test_harness_flags_requires.py:120` — `_REQUIRES_MAP_FROZEN` | **solo si la `FlagSpec` declara `requires=`** |
| 7 | `backend/api/devops.py::_health_payload()` (`:28-108`) + `DevOpsPage.tsx` `DEVOPS_SECTIONS` | solo si gatea una sección de UI |

**REGLA DURA:** una flag **default OFF NO debe declarar `default=False`** en la `FlagSpec`. Declarar cualquier default la vuelve `default_is_known` y `test_default_known_only_for_curated` exige que ese conjunto sea EXACTAMENTE `_CURATED_DEFAULTS_ON`, donde una flag OFF no puede entrar. El OFF vive **solo** en `config.py`. Precedente literal: `harness_flags.py:3169-3173`.

**REGLA DURA (R4):** `validate_requires_graph` (`harness_flags.py:5545-5569`) prohíbe cadenas: si `A.requires = B`, entonces `B.requires` debe ser `None`. Por eso las tres flags de este plan forman una **estrella**, no una cadena (ver §5.0.4).

**PLAIN_HELP:** los 4 campos tienen límites (`what` ≤200, `on_effect` ≤240, `off_effect` ≤240, `example` ≤300); `on_effect`/`off_effect` empiezan con `"Si "`; está prohibida la denylist congelada de jerga de `backend/tests/test_harness_flags_help.py:17-20` (`MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime`), las keys `SCREAMING_SNAKE` y las referencias `F1`/`F2`.

### 4.2 Reglas de test (no negociables)

- **Correr SIEMPRE por archivo, nunca la suite completa** (contaminación cross-file conocida en backend y en vitest).
- Backend: `backend\.venv\Scripts\python.exe -m pytest backend/tests/<archivo>.py -v` desde la raíz `Stacky Agents`.
- Frontend: `npx vitest run src/<ruta>.test.ts` **desde `frontend/`**.
- **Todo `backend/tests/test_*.py` nuevo debe registrarse en `HARNESS_TEST_FILES` — en los DOS runners**: `backend/scripts/run_harness_tests.sh:20` y `backend/scripts/run_harness_tests.ps1:15`. Si no, `backend/tests/test_harness_ratchet_meta.py` sale rojo (`:19`, `:49`).
- `backend/tests/test_harness_flags_help.py` arrastra **4 fallos ajenos preexistentes**: verificar que la key propia no esté entre las ofensoras y seguir.
- **Prohibido el falso verde:** cada fase declara su criterio binario y el comando exacto que lo produce. El output se lee, no se asume.

---

## 5. Fases

### F0 — Contrato del catálogo (backend, puro, sin IO)

**Objetivo.** Crear el tipo de dato de una acción DevOps y el catálogo semilla, sin ningún consumidor todavía. **Valor:** a partir de acá "qué se puede hacer en DevOps" es un dato inspeccionable, no una arqueología de JSX.

**Archivos a crear**
- `backend/services/devops_action_catalog.py`
- `backend/tests/test_devops_action_catalog.py`

**Archivos a editar (las 7 patas de la flag 1)**
- `backend/config.py`
- `backend/services/harness_flags.py`
- `backend/services/harness_flags_help.py`
- `backend/tests/test_harness_flags.py`
- `backend/scripts/run_harness_tests.sh`
- `backend/scripts/run_harness_tests.ps1`

**Contenido exacto de `backend/services/devops_action_catalog.py`**

```python
"""Plan 266 F0 — Catalogo unico de acciones DevOps.

PURO: sin flask, sin config, sin IO, sin red. Solo dataclasses + datos + lookups.
Es la fuente de VERDAD de la identidad y la seguridad de una accion; el COMO se
ejecuta vive en el binding del frontend (services/devopsActionBindings.ts), que
reusa los endpoints que ya existen. El ratchet de F8 exige igualdad de conjuntos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CATALOG_VERSION = "1"

EFFECTS = ("read", "write")
IMPACTS = ("none", "low", "high")
PARAM_TYPES = ("string", "int", "bool", "enum")

# Espejo CONGELADO de los ids de DEVOPS_SECTIONS (frontend/src/pages/DevOpsPage.tsx:145,
# ids en :149..:320). El ratchet de F8 lo compara contra el archivo .tsx real: si el
# frontend agrega o renombra una seccion y no se actualiza aca, el test sale ROJO.
DEVOPS_SECTION_IDS = (
    "resumen", "pipelines", "publicaciones", "ambientes", "agente", "servidores",
    "variables", "remote-console", "pr-review", "despliegues", "taller-compilacion",
    "publicador-soluciones", "inventario-pipelines", "pipeline-audit",
    "editar-pipeline", "matriz-entornos", "paquete-entrega",
)


@dataclass(frozen=True)
class ActionParam:
    name: str                       # snake_case, unico dentro de la accion
    type: str                       # uno de PARAM_TYPES
    label: str                      # español, para la UI
    required: bool = False
    enum_values: tuple[str, ...] = ()   # obligatorio y no vacio si type == "enum"
    default: str = ""               # "" = sin default


@dataclass(frozen=True)
class DevOpsAction:
    id: str                         # "devops.<dominio>.<verbo>", unico
    label: str                      # español, imperativo corto ("Disparar pipeline")
    summary: str                    # 1 frase: que hace, para la tarjeta de preview
    section_id: str | None          # id de DEVOPS_SECTION_IDS, o None si vive fuera del panel
    nav_path: str                   # deep-link donde el operador la ve manualmente
    effect: str                     # "read" | "write"
    impact: str                     # "none" | "low" | "high"
    targets_environment: bool       # True si actua sobre un entorno concreto del operador
    health_key: str                 # key de api/devops.py::_health_payload(), "" = siempre visible
    flag_key: str                   # key de la FlagSpec que la gatea, "" = ninguna
    params: tuple[ActionParam, ...] = ()
    phrases: tuple[str, ...] = ()   # frases de intencion en español (matcher determinista)


def get_action(action_id: str) -> DevOpsAction | None:
    """None si no existe. NUNCA lanza."""
    return _INDEX.get((action_id or "").strip())


def visible_actions(health: dict | None) -> list[DevOpsAction]:
    """Acciones cuyo health_key esta en True. health_key == "" => siempre visible.
    health None o vacio => solo las de health_key vacio. NUNCA lanza."""
    h = health or {}
    return [a for a in DEVOPS_ACTION_CATALOG
            if not a.health_key or h.get(a.health_key) is True]


def param_of(action: DevOpsAction, name: str) -> ActionParam | None:
    for p in action.params:
        if p.name == name:
            return p
    return None


def action_to_dict(a: DevOpsAction) -> dict:
    return {
        "id": a.id, "label": a.label, "summary": a.summary,
        "section_id": a.section_id, "nav_path": a.nav_path,
        "effect": a.effect, "impact": a.impact,
        "targets_environment": a.targets_environment,
        "health_key": a.health_key, "flag_key": a.flag_key,
        "params": [
            {"name": p.name, "type": p.type, "label": p.label,
             "required": p.required, "enum_values": list(p.enum_values),
             "default": p.default}
            for p in a.params
        ],
        "phrases": list(a.phrases),
    }


def catalog_payload(health: dict | None) -> dict:
    acts = visible_actions(health)
    return {
        "ok": True,
        "version": CATALOG_VERSION,
        "count": len(acts),
        "actions": [action_to_dict(a) for a in acts],
    }
```

**Catálogo semilla (23 acciones).** Se declara `DEVOPS_ACTION_CATALOG: tuple[DevOpsAction, ...]` con exactamente estas entradas. `PRJ = ActionParam(name="project", type="string", label="Proyecto", required=True)` se reusa; `ENV = ActionParam(name="environment", type="enum", label="Entorno", required=True, enum_values=("dev","qa","uat","prod"))`.

| # | `id` | `section_id` | `nav_path` | `effect` | `impact` | `targets_environment` | `health_key` | params extra |
|---|------|--------------|-----------|----------|----------|------------------------|--------------|--------------|
| 1 | `devops.overview.refresh` | `resumen` | `/devops/resumen` | read | none | false | `cockpit_enabled` | — |
| 2 | `devops.servers.list` | `servidores` | `/devops/servidores` | read | none | false | `servers_enabled` | — |
| 3 | `devops.servers.doctor` | `servidores` | `/devops/servidores` | read | none | false | `connection_doctor_enabled` | `server_alias` (string) |
| 4 | `devops.environments.list` | `ambientes` | `/devops/ambientes` | read | none | false | `environments_enabled` | — |
| 5 | `devops.variables.list` | `variables` | `/devops/variables` | read | none | false | `variables_enabled` | — |
| 6 | `devops.pipelines.inventory` | `inventario-pipelines` | `/devops/inventario-pipelines` | read | none | false | `pipeline_inventory_enabled` | — |
| 7 | `devops.pipelines.audit` | `pipeline-audit` | `/devops/pipeline-audit` | read | none | false | `pipeline_audit_enabled` | — |
| 8 | `devops.pipelines.env_matrix` | `matriz-entornos` | `/devops/matriz-entornos` | read | none | false | `env_matrix_enabled` | — |
| 9 | `devops.pipeline_edit.preview` | `editar-pipeline` | `/devops/editar-pipeline` | read | none | false | `pipeline_nl_edit_enabled` | `instruction` (string, required) |
| 10 | `devops.deployments.history` | `despliegues` | `/devops/despliegues` | read | none | false | `deployments_enabled` | — |
| 11 | `devops.publications.list` | `publicaciones` | `/devops/publicaciones` | read | none | false | `publications_enabled` | — |
| 12 | `devops.pr.list` | `pr-review` | `/devops/pr-review` | read | none | false | `pr_reviewer_enabled` | — |
| 13 | `devops.build.status` | `taller-compilacion` | `/devops/taller-compilacion` | read | none | false | `build_workshop_enabled` | — |
| 14 | `devops.handoff.preview` | `paquete-entrega` | `/devops/paquete-entrega` | read | none | false | `handoff_bundle_enabled` | — |
| 15 | `devops.logs.tail` | `None` | `/logs` | read | none | false | `""` | `lines` (int, default `"200"`) |
| 16 | `devops.incidents.list` | `None` | `/incidencias` | read | none | false | `""` | — |
| 17 | `devops.pipeline.trigger` | `pipelines` | `/devops/pipelines` | **write** | **high** | **true** | `trigger_enabled` | `ENV`, `pipeline_id` (string, required) |
| 18 | `devops.deployment.execute` | `despliegues` | `/devops/despliegues` | **write** | **high** | **true** | `deployments_execute_enabled` | `ENV`, `deployment_id` (string, required) |
| 19 | `devops.publication.run` | `publicaciones` | `/devops/publicaciones` | **write** | **high** | **true** | `one_click_publish_enabled` | `ENV`, `publication_id` (string, required) |
| 20 | `devops.solution.publish` | `publicador-soluciones` | `/devops/publicador-soluciones` | **write** | **high** | **true** | `solution_publisher_enabled` | `ENV`, `solution_path` (string, required) |
| 21 | `devops.remote_console.run` | `remote-console` | `/devops/remote-console` | **write** | **high** | **true** | `remote_console_enabled` | `ENV`, `server_alias` (string, required), `command` (string, required) |
| 22 | `devops.pipeline_edit.commit` | `editar-pipeline` | `/devops/editar-pipeline` | **write** | **high** | false | `pipeline_nl_edit_commit_enabled` | `branch` (string, required) |
| 23 | `devops.build.run` | `taller-compilacion` | `/devops/taller-compilacion` | **write** | **low** | false | `build_workshop_enabled` | `solution_path` (string, required) |

Todas llevan `PRJ` como primer param. `flag_key` de cada una es la flag ya existente que produce ese `health_key` (por ejemplo `devops.pipeline.trigger` ⇒ `STACKY_PIPELINE_TRIGGER_ENABLED`, `devops.pipeline_edit.commit` ⇒ `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`); las dos de `health_key=""` llevan `flag_key=""`.

**`phrases`** — mínimo 3 por acción, en español rioplatense, en minúscula y sin acentos (el matcher normaliza igual, pero así el dato es legible). Ejemplos literales:
- `devops.pipeline.trigger`: `("disparar la pipeline", "correr el pipeline", "ejecutar la pipeline", "lanzar el build de ci")`
- `devops.logs.tail`: `("ver los logs", "revisar logs", "mostrame el log", "ultimas lineas del log")`
- `devops.servers.doctor`: `("estado de los servidores", "chequear conexion", "diagnosticar el servidor", "esta caido el servidor")`
- `devops.deployment.execute`: `("desplegar", "hacer el deploy", "publicar el despliegue", "subir a produccion")`

**Flag 1 — `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (default ON)**

- `backend/config.py`, junto a las demás flags DevOps (patrón de `:1540-1541`):
  ```python
  STACKY_DEVOPS_ACTION_CATALOG_ENABLED: bool = os.getenv(
      "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", "true"
  ).lower() in ("1", "true", "yes")
  ```
- `backend/services/harness_flags.py`, `FlagSpec` nueva en el bloque DevOps:
  ```python
  FlagSpec(
      key="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
      type="bool",
      default=True,   # default ON: NINGUNA excepcion aplica. Solo LISTA lo que ya
                      # existe; no escribe en ningun lado, no llama a ningun modelo,
                      # no corre en reposo (se sirve a pedido de la pantalla) y no le
                      # saca ninguna decision al operador.
                      # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py:467).
      label="Catalogo de acciones DevOps",
      description=(
          "Plan 266 - declara en un solo lugar que se puede hacer en el panel DevOps "
          "(que accion, en que seccion, si lee o escribe, que impacto, sobre que "
          "entorno). Lo consumen los botones, la paleta de comandos y el asistente. "
          "OFF: /api/devops/actions/catalog devuelve 404 y las tres superficies "
          "quedan como hoy."
      ),
      group="global",
      env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
  ),
  ```
  **SIN `requires=`** — es el master de la estrella (regla R4, §4.1).
- `_CATEGORY_KEYS["devops"]` (`harness_flags.py:223`): agregar `"STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`.
- `PLAIN_HELP` (`harness_flags_help.py:25`):
  ```python
  "STACKY_DEVOPS_ACTION_CATALOG_ENABLED": PlainHelp(
      what="Arma una lista unica de todo lo que se puede hacer en el panel de DevOps, para que los botones, el buscador de comandos y el asistente ofrezcan siempre lo mismo.",
      on_effect="Si la activas: la misma accion aparece con el mismo nombre y la misma advertencia en todos lados.",
      off_effect="Si la apagas: cada pantalla vuelve a ofrecer su propia lista, y el buscador de comandos deja de ofrecer acciones.",
      example="Es como el menu unico de un restaurante: la carta de la mesa, la del mostrador y la del delivery dicen exactamente lo mismo.",
  ),
  ```
  (verificado contra la denylist de `test_harness_flags_help.py:17-20`: no usa ninguna de las 15 palabras prohibidas, no cita keys ni fases).
- `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`): agregar `"STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`.
- `HARNESS_TEST_FILES` en `run_harness_tests.sh:20` **y** `run_harness_tests.ps1:15`: agregar `tests/test_devops_action_catalog.py`.

**Tests PRIMERO — `backend/tests/test_devops_action_catalog.py`**

1. `test_catalog_no_vacio_y_al_menos_23` — `len(DEVOPS_ACTION_CATALOG) >= 23`.
2. `test_ids_unicos` — `len({a.id for a in ...}) == len(DEVOPS_ACTION_CATALOG)`.
3. `test_ids_con_prefijo_devops` — todo `a.id.startswith("devops.")` y tiene exactamente 2 puntos.
4. `test_effect_e_impact_en_vocabulario` — `a.effect in EFFECTS and a.impact in IMPACTS`.
5. `test_section_id_conocida_o_none` — `a.section_id is None or a.section_id in DEVOPS_SECTION_IDS`.
6. `test_nav_path_arranca_con_slash` — `a.nav_path.startswith("/")`.
7. `test_todas_declaran_project` — `param_of(a, "project") is not None` para toda acción.
8. `test_params_nombres_unicos_por_accion`.
9. `test_enum_declara_valores` — `p.type != "enum" or len(p.enum_values) > 0`.
10. `test_phrases_minimo_tres` — `len(a.phrases) >= 3` para toda acción.
11. `test_get_action_desconocida_devuelve_none` — `get_action("nope") is None`, `get_action("") is None`, `get_action(None) is None` (no lanza).
12. `test_visible_actions_filtra_por_health` — con `health={"servers_enabled": True}` aparecen `devops.servers.list` y las de `health_key=""`, y NO aparece `devops.pipeline.trigger`.
13. `test_visible_actions_health_none` — `visible_actions(None)` devuelve solo las de `health_key==""` (2 acciones) y no lanza.
14. `test_catalog_payload_serializa` — `json.dumps(catalog_payload({...}))` no lanza y `payload["version"] == "1"`.
15. `test_modulo_no_importa_flask_ni_config` — leer el propio `.py` como texto y afirmar que no contiene `"import flask"`, `"from flask"` ni `"import config"`.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_catalog.py -v`
**Aceptación binaria:** 15 passed, 0 failed. Además `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -v` (56 passed) y `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_ratchet_meta.py -v` (4 passed).

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` — **default ON**.
**Runtimes:** Codex / Claude Code / Copilot — **idéntico**; el módulo es datos puros, no ejecuta nada. Sin fallback necesario.
**Trabajo del operador: ninguno.**

---

### F1 — Endpoint del catálogo y health key

**Objetivo.** Servir el catálogo por HTTP para que el frontend lo consuma en vez de duplicarlo. **Valor:** el frontend no reescribe metadatos de seguridad.

**Archivos a crear**
- `backend/api/devops_actions.py`
- `backend/tests/test_devops_actions_api.py`

**Archivos a editar**
- `backend/api/__init__.py` — import junto a `:49`/`:54` y `register_blueprint` en el bloque de `:85+`.
- `backend/api/devops.py` — `_health_payload()` (`:28-108`): agregar antes del cierre de `:108`.

```python
# backend/api/devops_actions.py
"""api/devops_actions.py - Catalogo de acciones DevOps (Plan 266).

url_prefix="/devops/actions" -> rutas /api/devops/actions/... (NO poner /api/ en el
prefix; mismo gotcha C2 del plan 73, ver api/devops_agent.py:3-4).
"""
from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("devops_actions", __name__, url_prefix="/devops/actions")


def _catalog_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)


@bp.get("/catalog")
def get_catalog():
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    from api.devops import _health_payload
    from services.devops_action_catalog import catalog_payload
    return jsonify(catalog_payload(_health_payload()))
```

En `_health_payload()` (`api/devops.py`, antes del `}` de `:108`):

```python
"action_catalog_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)
),  # Plan 266 - catalogo de acciones (solo lectura)
"action_nl_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_ACTION_NL_ENABLED", False)
),  # Plan 266 - lenguaje natural -> propuesta de accion
"agent_action_run_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", False)
),  # Plan 266 - ejecutar desde una propuesta lo que ESCRIBE (default OFF)
```

Las tres keys se agregan **en F1** aunque las flags 2 y 3 se declaren en F3 y F6: `getattr(..., False)` tolera el atributo ausente, y `test_bootstrap_health_matches_health_endpoint` compara `/health` contra `/bootstrap`, que comparten la misma función — no hay riesgo de divergencia. Registrar en `config.py` los tres atributos en F1 (con sus defaults finales) evita tres ediciones del mismo archivo.

**Tests (parte 1 de `test_devops_actions_api.py`)**
1. `test_catalog_flag_off_404` — con `monkeypatch.setattr(config.config, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)` ⇒ `GET /api/devops/actions/catalog` da **404** con `{"error":"devops_action_catalog_disabled"}`.
2. `test_catalog_flag_on_200_y_shape` — 200; `body["ok"] is True`; `body["version"] == "1"`; `isinstance(body["actions"], list)`; cada item tiene las 11 keys de `action_to_dict`.
3. `test_catalog_filtra_por_health` — con todas las flags DevOps en False, solo aparecen las 2 acciones de `health_key==""`.
4. `test_health_expone_las_tres_keys_nuevas` — `GET /api/devops/health` incluye `action_catalog_enabled`, `action_nl_enabled`, `agent_action_run_enabled`.
5. `test_bootstrap_health_paridad` — `/bootstrap` y `/health` devuelven el mismo subconjunto de esas 3 keys.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v`
**Aceptación binaria:** los 5 tests de F1 en verde. Además `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops.py -v` sigue verde (paridad de `/health`).
**Registro:** agregar `tests/test_devops_actions_api.py` a `HARNESS_TEST_FILES` en el `.sh` y en el `.ps1`.

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` — default ON.
**Runtimes:** idéntico en los 3; es un `GET` sin modelo.
**Trabajo del operador: ninguno.**

---

### F2 — Matcher de intención determinista (sin modelo)

**Objetivo.** Traducir una frase en español a una o más acciones candidatas **sin llamar a ningún modelo**. **Valor:** es la pata que da paridad real a Copilot y el fallback cuando el runtime no está disponible.

**Archivos a crear**
- `backend/services/devops_action_matcher.py`
- `backend/tests/test_devops_action_matcher.py`

```python
"""Plan 266 F2 — Matcher de intencion DETERMINISTA. Sin modelo, sin red, sin IO.

Es el piso de paridad: con GitHub Copilot (o sin runtime disponible) este matcher
es TODO el motor de intencion, y alcanza para proponer y previsualizar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from services.devops_action_catalog import DevOpsAction

MIN_SCORE = 0.6          # por debajo => no hay match
AMBIGUITY_DELTA = 0.10   # si top1 - top2 < esto => needs_disambiguation
MAX_MATCHES = 3

_NON_WORD = re.compile(r"[^a-z0-9ñ ]+")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class ActionMatch:
    action_id: str
    score: float          # 0.0 .. 1.0
    matched_phrase: str


def normalize_text(text: str | None) -> str:
    """minusculas + sin acentos + sin puntuacion + espacios colapsados. NUNCA lanza."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", str(text).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _NON_WORD.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def _phrase_score(norm_text: str, phrase: str) -> float:
    """Cobertura de tokens de la frase presentes en el texto, + bonus por substring.
    Determinista y acotado a [0,1]."""
    tokens = [t for t in normalize_text(phrase).split(" ") if t]
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in norm_text.split(" "))
    base = hits / len(tokens)
    if normalize_text(phrase) and normalize_text(phrase) in norm_text:
        base = min(1.0, base + 0.15)
    return round(base, 4)


def match_intent(text: str | None, actions: list[DevOpsAction]) -> list[ActionMatch]:
    """Devuelve hasta MAX_MATCHES matches con score >= MIN_SCORE, ordenados por
    score DESC y, ante empate exacto, por el ORDEN DEL CATALOGO (estable).
    Lista vacia = no entendi. NUNCA lanza."""
    norm = normalize_text(text)
    if not norm:
        return []
    scored: list[tuple[float, int, ActionMatch]] = []
    for idx, a in enumerate(actions or []):
        best, best_phrase = 0.0, ""
        for candidate in (*a.phrases, a.label):
            s = _phrase_score(norm, candidate)
            if s > best:
                best, best_phrase = s, candidate
        if best >= MIN_SCORE:
            scored.append((best, idx, ActionMatch(a.id, best, best_phrase)))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [m for _, _, m in scored[:MAX_MATCHES]]


def is_ambiguous(matches: list[ActionMatch]) -> bool:
    """True si hay >= 2 matches y la diferencia de score es menor a AMBIGUITY_DELTA."""
    if len(matches) < 2:
        return False
    return (matches[0].score - matches[1].score) < AMBIGUITY_DELTA
```

**Tests — `backend/tests/test_devops_action_matcher.py`**
1. `test_normalize_quita_acentos_y_puntuacion` — `normalize_text("¿Disparar la Pipeline?") == "disparar la pipeline"`.
2. `test_normalize_none_y_vacio` — `normalize_text(None) == ""`, `normalize_text("   ") == ""`.
3. `test_match_frase_exacta` — `"disparar la pipeline"` ⇒ `matches[0].action_id == "devops.pipeline.trigger"`.
4. `test_match_con_acentos_y_mayusculas` — `"Quiero DISPARAR la píplain"` no matchea (score bajo); `"Quiero disparar la pipeline de QA"` sí.
5. `test_match_parcial_supera_umbral` — `"ver los logs"` ⇒ `devops.logs.tail`.
6. `test_sin_match_devuelve_vacio` — `"receta de milanesas"` ⇒ `[]`.
7. `test_texto_vacio_devuelve_vacio` — `match_intent("", CAT) == []` y `match_intent(None, CAT) == []`.
8. `test_orden_estable_ante_empate` — construir 2 acciones sintéticas con la misma frase y verificar que gana la de índice menor, **corriendo 5 veces con el mismo input y comparando la salida**.
9. `test_tope_de_tres_matches` — nunca devuelve más de 3.
10. `test_is_ambiguous_true_y_false` — dos matches con 0.90/0.85 ⇒ `True`; con 0.90/0.60 ⇒ `False`; con 1 match ⇒ `False`; con 0 ⇒ `False`.
11. `test_no_importa_flask_ni_red` — leer el `.py` y afirmar que no contiene `"requests"`, `"flask"` ni `"urllib"`.
12. `test_score_acotado` — para 200 frases generadas, `0.0 <= score <= 1.0`.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_matcher.py -v`
**Aceptación binaria:** 12 passed. **Registro:** `tests/test_devops_action_matcher.py` en `HARNESS_TEST_FILES` (`.sh` y `.ps1`).

**Flag:** ninguna propia (es una función pura consumida por F3, gateada por `STACKY_DEVOPS_ACTION_NL_ENABLED`).
**Runtimes:** **idéntico en los 3** — no usa modelo. Ese es el punto de la fase.
**Trabajo del operador: ninguno.**

---

### F3 — `ActionProposal` + `POST /propose` + `POST /preview` (paridad 3 runtimes)

**Objetivo.** Que el agente devuelva una **acción tipada** en vez de prosa, con el molde de `IntentBrief`. **Valor:** cierra KPI-4 y KPI-5.

**Archivos a crear**
- `backend/services/devops_action_proposal.py`

**Archivos a editar**
- `backend/api/devops_actions.py` (agrega `/propose` y `/preview`)
- `backend/tests/test_devops_actions_api.py` (agrega los tests de F3)
- las 7 patas de la flag 2 (`config.py` ya la tiene desde F1; faltan `harness_flags.py` ×2, `harness_flags_help.py`, `test_harness_flags.py`, `test_harness_flags_requires.py`)

```python
"""Plan 266 F3 — Contrato de propuesta de accion.

Calca el molde de services/intent_preflight.py:39-47 (IntentBrief) a proposito:
mismos campos de intencion (open_questions, confidence, version) sobre un objeto
que ademas nombra la ACCION. NO se inventa un contrato nuevo.
"""
from __future__ import annotations

from dataclasses import dataclass

from services.devops_action_catalog import DevOpsAction, get_action, param_of
from services.devops_action_matcher import ActionMatch, is_ambiguous, match_intent

PROPOSAL_VERSION = "1"

_IMPACT_LABEL = {"none": "sin impacto", "low": "impacto bajo", "high": "impacto alto"}

BLOCKED_NONE = ""
BLOCKED_NO_MATCH = "no_match"
BLOCKED_AMBIGUOUS = "ambiguous"
BLOCKED_MISSING_PARAMS = "missing_params"
BLOCKED_FLAG_OFF = "flag_off"
BLOCKED_AGENT_WRITE_DISABLED = "agent_write_disabled"


@dataclass(frozen=True)
class ProposalParam:
    name: str
    value: str
    source: str   # "operator" | "default" | "missing"


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    label: str
    summary: str
    section_id: str | None
    nav_path: str
    effect: str
    impact: str
    targets_environment: bool
    environment: str            # "" si la accion no apunta a un entorno
    params: list[ProposalParam]
    what_will_happen: str       # 1 frase determinista en español
    open_questions: list[str]   # 1 por param required faltante
    alternatives: list[str]     # action_ids alternativos si hubo ambiguedad
    confidence: float           # score del matcher, 0.0 .. 1.0
    needs_confirmation: bool    # SIEMPRE True si effect == "write"
    blocked_reason: str         # una de las constantes BLOCKED_*
    version: str = PROPOSAL_VERSION


def describe(action: DevOpsAction, environment: str) -> str:
    """Frase determinista de 'que va a pasar'. Sin modelo. NUNCA lanza."""
    donde = f"sobre el entorno {environment}" if environment else "sobre el proyecto activo"
    efecto = ("Escribe en un sistema real del operador."
              if action.effect == "write"
              else "Solo lectura: no cambia nada.")
    return f"{action.label} {donde}. {_IMPACT_LABEL[action.impact]}. {efecto}"


def build_proposal(
    action: DevOpsAction,
    supplied: dict,
    confidence: float,
    alternatives: list[str],
    agent_write_enabled: bool,
) -> ActionProposal:
    """Arma la propuesta. NO ejecuta nada. NUNCA lanza."""
    params: list[ProposalParam] = []
    missing: list[str] = []
    for p in action.params:
        raw = (supplied or {}).get(p.name)
        if raw is not None and str(raw).strip():
            params.append(ProposalParam(p.name, str(raw).strip(), "operator"))
        elif p.default:
            params.append(ProposalParam(p.name, p.default, "default"))
        else:
            params.append(ProposalParam(p.name, "", "missing"))
            if p.required:
                missing.append(p.name)

    env = ""
    if action.targets_environment:
        for pp in params:
            if pp.name == "environment" and pp.value:
                env = pp.value
                break

    blocked = BLOCKED_NONE
    if action.effect == "write" and not agent_write_enabled:
        blocked = BLOCKED_AGENT_WRITE_DISABLED
    elif missing:
        blocked = BLOCKED_MISSING_PARAMS

    return ActionProposal(
        action_id=action.id, label=action.label, summary=action.summary,
        section_id=action.section_id, nav_path=action.nav_path,
        effect=action.effect, impact=action.impact,
        targets_environment=action.targets_environment, environment=env,
        params=params, what_will_happen=describe(action, env),
        open_questions=[
            f"¿Qué valor uso para «{(param_of(action, n).label if param_of(action, n) else n)}»?"
            for n in missing
        ],
        alternatives=alternatives, confidence=round(float(confidence), 4),
        needs_confirmation=(action.effect == "write"),
        blocked_reason=blocked,
    )


def proposal_to_dict(p: ActionProposal) -> dict: ...   # serializacion 1:1, listas planas
```

**Endpoints nuevos en `backend/api/devops_actions.py`**

```python
@bp.post("/propose")
def propose_action():
    """Frase en español -> ActionProposal tipada. DETERMINISTA: no llama a ningun
    modelo. Funciona identico en Codex CLI, Claude Code CLI y GitHub Copilot Pro:
    el runtime del body se ACEPTA y se ignora para el matching (a diferencia de
    api/devops_agent.py:69-78, que devuelve 400 para copilot)."""
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    if not getattr(_config.config, "STACKY_DEVOPS_ACTION_NL_ENABLED", False):
        return jsonify({"error": "devops_action_nl_disabled"}), 404
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text es obligatorio"}), 400
    supplied = body.get("params") if isinstance(body.get("params"), dict) else {}

    from api.devops import _health_payload
    from services.devops_action_catalog import get_action, visible_actions
    from services.devops_action_matcher import is_ambiguous, match_intent
    from services import devops_action_proposal as dap

    health = _health_payload()
    actions = visible_actions(health)
    matches = match_intent(text, actions)
    if not matches:
        return jsonify({"ok": True, "proposal": None,
                        "blocked_reason": dap.BLOCKED_NO_MATCH,
                        "suggestions": [a.label for a in actions[:5]]})

    agent_write = bool(getattr(_config.config,
                               "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", False))
    top = get_action(matches[0].action_id)
    alts = [m.action_id for m in matches[1:]] if is_ambiguous(matches) else []
    prop = dap.build_proposal(top, supplied, matches[0].score, alts, agent_write)
    if alts:
        prop = replace(prop, blocked_reason=dap.BLOCKED_AMBIGUOUS)
    return jsonify({"ok": True, "proposal": dap.proposal_to_dict(prop)})


@bp.post("/preview")
def preview_action():
    """action_id + params EXPLICITOS -> la misma ActionProposal, sin matching.
    Es lo que llama la tarjeta cuando el operador corrige un parametro.
    SOLO LECTURA: no ejecuta nada, jamas."""
    # mismos gates que /propose; 404 si el action_id no existe o no esta en
    # visible_actions(health) (una accion gateada NO se previsualiza).
```

**Flag 2 — `STACKY_DEVOPS_ACTION_NL_ENABLED` (default ON)**

- `config.py`: `os.getenv("STACKY_DEVOPS_ACTION_NL_ENABLED", "true")`.
- `FlagSpec`: `default=True`, `requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`, `group="global"`, `env_only=False`.
  Comentario obligatorio en la línea del `default`: *default ON — ninguna excepción aplica: solo INTERPRETA una frase que el operador acaba de escribir y devuelve una propuesta; no corre en reposo (no hay loop ni daemon: se dispara por request), no llama a ningún modelo (el matcher es determinista) y no escribe absolutamente nada. Curada en `_CURATED_DEFAULTS_ON`.*
- `_CATEGORY_KEYS["devops"]`, `PLAIN_HELP`, `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`).
- **`_REQUIRES_MAP_FROZEN`** (`backend/tests/test_harness_flags_requires.py:120`): agregar `"STACKY_DEVOPS_ACTION_NL_ENABLED": "STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`. El assert de `:316` es de **igualdad de mapas**: olvidarla es rojo, y agregarla sin `requires` también.

**Tests (parte 2 de `test_devops_actions_api.py`)**
6. `test_propose_nl_flag_off_404`.
7. `test_propose_sin_text_400`.
8. `test_propose_devuelve_accion_tipada` — `{"text":"quiero ver los logs","params":{"project":"Pacifico"}}` ⇒ `proposal["action_id"] == "devops.logs.tail"`, `effect == "read"`, `needs_confirmation is False`, `blocked_reason == ""`.
9. `test_propose_write_marca_needs_confirmation` — `"disparar la pipeline"` con todas las flags ON ⇒ `effect == "write"`, `impact == "high"`, `needs_confirmation is True`.
10. `test_propose_write_bloqueada_si_run_flag_off` — con `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=False` ⇒ `blocked_reason == "agent_write_disabled"` y **la propuesta igual se devuelve** (el operador puede verla y navegar al panel).
11. `test_propose_param_faltante_genera_pregunta` — sin `environment` ⇒ `blocked_reason == "missing_params"` y `open_questions` tiene 1 entrada que nombra "Entorno".
12. `test_propose_sin_match_no_lanza` — `"receta de milanesas"` ⇒ 200, `proposal is None`, `blocked_reason == "no_match"`, `suggestions` no vacío.
13. **`test_propose_copilot_mismo_resultado_que_cli`** — llamar 3 veces con `runtime` `"codex_cli"`, `"claude_code_cli"` y `"copilot"` y el mismo `text`; los 3 devuelven **200** y **el mismo `proposal` byte a byte**. Este test es el que prueba KPI-5 y el que hace fallar cualquier regresión que reintroduzca el 400 de `devops_agent.py:69-78`.
14. `test_preview_action_id_desconocido_404`.
15. `test_preview_accion_gateada_404` — una acción cuyo `health_key` está en False no se previsualiza.
16. `test_preview_no_ejecuta_nada` — monkeypatchear los módulos de ejecución para que exploten si se los llama; el endpoint responde 200 sin tocarlos.
17. `test_what_will_happen_nombra_entorno_e_impacto` — la frase contiene el entorno declarado y una de las 3 etiquetas de impacto.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v`
**Aceptación binaria:** 17 passed (5 de F1 + 12 de F3), 0 failed. Más: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -v` (9 passed).

**Flag:** `STACKY_DEVOPS_ACTION_NL_ENABLED` — **default ON**.
**Runtimes:**
- **Codex CLI** — el matcher determinista responde; F6 puede además pedirle al runtime un enriquecimiento opcional.
- **Claude Code CLI** — idéntico.
- **GitHub Copilot Pro** — **idéntico y completo**: el camino no llama a ningún modelo. *Fallback explícito:* si en el futuro se agrega enriquecimiento por LLM y el runtime no está disponible, se captura `PreflightRuntimeUnavailable` (`intent_preflight.py:25-26`) y se devuelve la propuesta determinista con `confidence` sin modificar. **Nunca un error.**
**Trabajo del operador: ninguno.**

---

### F4 — Espejo tipado, bindings y `runDevOpsAction` (frontend puro)

**Objetivo.** Un único ejecutor de acciones en el frontend, con la confirmación derivada del catálogo. **Valor:** cierra KPI-6 y KPI-7; después de F4 ninguna superficie necesita saber cómo se confirma.

**Archivos a crear**
- `frontend/src/services/devopsActionTypes.ts`
- `frontend/src/services/devopsActionRunner.ts`
- `frontend/src/services/devopsActionBindings.ts`
- `frontend/src/services/devopsActionRunner.test.ts`
- `frontend/src/services/devopsActionBindings.test.ts`

```ts
// frontend/src/services/devopsActionTypes.ts
// Plan 266 F4 — Espejo TIPADO del catalogo backend. Sin React, sin DOM.
export type DevOpsActionEffect = 'read' | 'write';
export type DevOpsActionImpact = 'none' | 'low' | 'high';

export interface DevOpsActionParamMeta {
  name: string; type: 'string' | 'int' | 'bool' | 'enum'; label: string;
  required: boolean; enum_values: string[]; default: string;
}

export interface DevOpsActionMeta {
  id: string; label: string; summary: string;
  section_id: string | null; nav_path: string;
  effect: DevOpsActionEffect; impact: DevOpsActionImpact;
  targets_environment: boolean; health_key: string; flag_key: string;
  params: DevOpsActionParamMeta[]; phrases: string[];
}
```

```ts
// frontend/src/services/devopsActionRunner.ts
// Plan 266 F4 — Ejecutor UNICO. La confirmacion se DERIVA del catalogo, no se
// escribe a mano. Reusa confirmGateway (services/confirmGateway.ts:10-21) tal cual.
import type { ConfirmFn, ConfirmRequest } from './confirmGateway';
import type { DevOpsActionMeta } from './devopsActionTypes';

export interface DevOpsActionReceipt {
  actionId: string; ok: boolean; summary: string; detail: string;
  navPath: string; startedAt: number; finishedAt: number;
  confirmed: boolean;   // false = el operador dijo que no, o no habia gateway
}

export interface DevOpsActionRunContext {
  askConfirm: ConfirmFn;
  navigate: (path: string) => void;
  now: () => number;                 // inyectable => testeable sin fake timers
  onReceipt?: (r: DevOpsActionReceipt) => void;
}

export interface DevOpsActionBinding {
  id: string;
  run: (params: Record<string, string>, ctx: DevOpsActionRunContext)
    => Promise<{ ok: boolean; summary: string; detail?: string }>;
}

const IMPACT_TEXT: Record<string, string> = {
  none: 'Sin impacto', low: 'Impacto bajo', high: 'Impacto alto',
};

/** null si effect === 'read': NO se molesta al operador para leer.
 *  tone 'danger' <=> impact 'high'. El mensaje SIEMPRE nombra los 4 datos que
 *  el operador pidio ver: accion, entorno, impacto y que va a pasar. */
export function confirmRequestFor(
  a: DevOpsActionMeta, params: Record<string, string>
): ConfirmRequest | null {
  if (a.effect === 'read') return null;
  const env = a.targets_environment ? (params.environment || 'sin entorno declarado') : '';
  const donde = env ? ` sobre el entorno ${env}` : '';
  return {
    title: a.label,
    message: `${a.summary}${donde}. ${IMPACT_TEXT[a.impact]}. Esta acción escribe en un sistema real y no se puede deshacer sola.`,
    confirmLabel: a.label,
    tone: a.impact === 'high' ? 'danger' : 'default',
  };
}

/** Faltan params required => lista de nombres. Vacia = se puede correr. */
export function missingRequired(
  a: DevOpsActionMeta, params: Record<string, string>
): string[] {
  return a.params
    .filter((p) => p.required && !String(params[p.name] ?? '').trim())
    .map((p) => p.name);
}

/** Ejecuta. NUNCA lanza: siempre devuelve un recibo.
 *  Orden EXACTO e inviolable:
 *    1. binding ausente        -> recibo ok:false, NO se ejecuta nada
 *    2. params required faltan -> recibo ok:false, NO se confirma ni se ejecuta
 *    3. confirmRequestFor != null -> askConfirm; si devuelve false -> recibo
 *       ok:false confirmed:false y el binding NO se llama
 *    4. binding.run(...)       -> recibo con su resultado
 *    5. si run() lanza         -> recibo ok:false con el mensaje del error */
export async function runDevOpsAction(
  action: DevOpsActionMeta,
  params: Record<string, string>,
  binding: DevOpsActionBinding | undefined,
  ctx: DevOpsActionRunContext
): Promise<DevOpsActionReceipt> { /* ... */ }
```

```ts
// frontend/src/services/devopsActionBindings.ts
// Plan 266 F4 — El COMO. Cada binding llama al MISMO endpoint que ya usa el boton
// manual de su seccion. PROHIBIDO agregar endpoints nuevos aca.
export const DEVOPS_ACTION_BINDINGS: Record<string, DevOpsActionBinding> = {
  'devops.overview.refresh': { id: 'devops.overview.refresh', run: async (p, ctx) => { ... } },
  // ... una entrada por cada uno de los 23 ids del catalogo
};
export function bindingFor(id: string): DevOpsActionBinding | undefined {
  return DEVOPS_ACTION_BINDINGS[id];
}
```

**Regla de implementación de los bindings (para no equivocarse):** cada binding llama a la función de `frontend/src/api/endpoints.ts` que **ya usa** el botón manual de esa sección. Si un id del catálogo no tiene endpoint propio porque su acción es "abrir la pantalla y filtrar" (caso de `devops.logs.tail` e `devops.incidents.list`), el binding hace `ctx.navigate(nav_path)` y devuelve `{ok:true, summary:"Abierto en <ruta>"}`. **Nunca** se inventa un endpoint.

**Tests — `frontend/src/services/devopsActionRunner.test.ts`** (11 casos)
1. `confirmRequestFor` con `effect:'read'` ⇒ `null`.
2. `confirmRequestFor` con `impact:'high'` ⇒ `tone === 'danger'`.
3. `confirmRequestFor` con `impact:'low'` ⇒ `tone === 'default'`.
4. el `message` contiene el entorno cuando `targets_environment` y `params.environment` está.
5. el `message` dice `'sin entorno declarado'` cuando `targets_environment` y falta el param.
6. `missingRequired` detecta faltantes y devuelve `[]` cuando están todos.
7. **`runDevOpsAction` con `askConfirm = denyByDefault` y `effect:'write'` NO llama al binding** (spy con 0 llamadas) y devuelve `confirmed:false, ok:false`.
8. `runDevOpsAction` con `effect:'read'` **no llama a `askConfirm`** (spy con 0 llamadas) y sí llama al binding.
9. `runDevOpsAction` con binding `undefined` devuelve `ok:false` y **no lanza**.
10. `runDevOpsAction` con un binding cuyo `run` lanza devuelve `ok:false` con el mensaje, **no propaga**.
11. `runDevOpsAction` con `missingRequired` no vacío ⇒ `ok:false`, `askConfirm` **no** se llama y el binding **no** se llama.

**Tests — `frontend/src/services/devopsActionBindings.test.ts`** (3 casos)
1. Toda clave del record cumple `/^devops\.[a-z_]+\.[a-z_]+$/`.
2. Para toda clave `k`, `DEVOPS_ACTION_BINDINGS[k].id === k` (no hay ids desalineados).
3. `bindingFor('no-existe')` devuelve `undefined` sin lanzar.

**Comando:** desde `frontend/`: `npx vitest run src/services/devopsActionRunner.test.ts` y `npx vitest run src/services/devopsActionBindings.test.ts`
**Aceptación binaria:** 11 + 3 passed. Más `npx tsc --noEmit` sin errores.

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (la UI solo carga el catálogo si `health.action_catalog_enabled === true`).
**Runtimes:** irrelevante — código de UI, no llama a ningún modelo. Idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F5 — Superficie 1: la paleta de comandos (el "mañana" del comentario)

**Objetivo.** Que la paleta ejecute acciones DevOps, no solo navegue. **Valor:** cierra KPI-2 y cumple, cinco planes después, la promesa escrita en `entityActions.ts:3-5`.

**Archivos a editar**
- `frontend/src/components/commandPaletteData.ts`
- `frontend/src/components/CommandPalette.tsx` (260 líneas)

**Archivos a crear**
- `frontend/src/components/__tests__/commandPaletteDevopsActions.test.ts`

Cambios exactos en `commandPaletteData.ts`:

1. Agregar `"devops-action"` al union `CommandKind` (`:10-19`) — **al final**, para no alterar el orden que otros módulos puedan asumir. `EntityKind` (`entityActions.ts:15`) usa `Extract<..., "execution"|"ticket">`, así que **no se ve afectado**.
2. Agregar la entrada `'devops-action': '⚡'` a `DEEP_ICONS` (`:91-97`).
3. Función nueva, pura:
   ```ts
   /** Plan 266 F5 — Convierte el catalogo en Command[] para la paleta.
    *  - Solo entran acciones cuyo health_key esta ON (ya viene filtrado por el
    *    servidor, pero se re-filtra por defensa).
    *  - Las de effect 'write' llevan el hint con el impacto y el entorno, para que
    *    el operador NO las dispare de memoria creyendo que son inocuas.
    *  - `run` NO ejecuta: delega en onRun(action), que en CommandPalette.tsx llama
    *    a runDevOpsAction (que a su vez confirma). La paleta jamas confirma sola. */
   export function devopsActionCommands(
     actions: DevOpsActionMeta[],
     onRun: (a: DevOpsActionMeta) => void
   ): Command[]
   ```
   Cada `Command` resultante: `id: \`devops-action-${a.id}\``, `kind: 'devops-action'`, `icon: a.effect === 'write' ? '⚠️' : '⚡'`, `label: a.label`, `hint: a.effect === 'write' ? \`Escribe · ${IMPACT_TEXT[a.impact]}\` : a.summary`, `run: () => onRun(a)`.

En `CommandPalette.tsx`: cargar el catálogo con un `GET /api/devops/actions/catalog` **una sola vez al abrir la paleta** (nunca en un intervalo — el ratchet de sondeo del 239 F6 lo prohíbe), concatenar `devopsActionCommands(...)` después de `NAV_COMMANDS`, y cablear `onRun` a `runDevOpsAction` con el `askConfirm` real de la app. Si el `GET` falla o devuelve 404, la paleta queda **exactamente como hoy** (solo navegación), sin banner ni error.

**Tests — `commandPaletteDevopsActions.test.ts`** (7 casos)
1. `devopsActionCommands([], noop)` ⇒ `[]`.
2. Con 12 acciones ⇒ 12 comandos, todos con `kind === 'devops-action'`.
3. Todos los `id` empiezan con `devops-action-` y son únicos.
4. Una acción `write` con `impact:'high'` produce `icon === '⚠️'` y un `hint` que contiene `'Escribe'`.
5. Una acción `read` produce `icon === '⚡'` y `hint === a.summary`.
6. `run()` invoca `onRun` con la acción **y no hace nada más** (spy: 1 llamada, y ningún otro efecto).
7. `fuzzyScore` (`commandPaletteData.ts:31-49`) sigue devolviendo lo mismo para 6 pares de entrada conocidos — **test de no-regresión de la función existente**.

**Comando:** desde `frontend/`: `npx vitest run src/components/__tests__/commandPaletteDevopsActions.test.ts` y, por no-regresión, `npx vitest run src/components/__tests__/commandPaletteData.test.ts`
**Aceptación binaria:** 7 passed + los tests preexistentes de `commandPaletteData.test.ts` en verde (mismo número que antes del cambio).

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED`. Con OFF, el `GET` da 404 y la paleta queda idéntica a hoy.
**Runtimes:** idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F6 — Superficie 2: la consola de acciones del agente (propuesta → confirmación → recibo)

**Objetivo.** Reemplazar la prosa del agente por una tarjeta que muestra **qué acción, sobre qué entorno, qué impacto y qué resultado**. **Valor:** es literalmente lo que pidió el operador.

**Archivos a crear**
- `frontend/src/components/devops/DevOpsActionProposalCard.tsx`
- `frontend/src/components/devops/DevOpsActionConsole.tsx`
- `frontend/src/components/devops/devopsActionConsoleModel.ts` (lógica pura)
- `frontend/src/components/devops/devopsActionConsoleModel.test.ts`

**Archivos a editar**
- `frontend/src/components/devops/DevOpsAgentSection.tsx` (228 líneas) — montar `DevOpsActionConsole` **encima** del chat existente, sin borrarlo.
- las 7 patas de la flag 3.

**Contrato visual de la tarjeta (obligatorio, en este orden vertical):**
1. **Qué acción** — `label` en el título + `summary` debajo.
2. **Sobre qué entorno** — chip con `environment` si `targets_environment`; si está vacío, chip rojo `"Falta declarar el entorno"`.
3. **Cuál es el impacto** — badge con el texto de `IMPACT_TEXT` y `tone` `danger` si `impact === 'high'`.
4. **Qué va a pasar** — `what_will_happen`, textual, del backend.
5. **Parámetros** — tabla `nombre / valor / origen`; los de `source:'missing'` son campos editables.
6. **Preguntas abiertas** — `open_questions`, una por línea, si las hay.
7. **Alternativas** — si `blocked_reason === 'ambiguous'`, botones para elegir entre `alternatives`.
8. **Acciones** — `[Ejecutar]` (deshabilitado si `blocked_reason !== ''`) + `[Ver en el panel]` (siempre habilitado, navega a `nav_path`).
9. **Recibo** — tras ejecutar: ✅/❌, `summary`, `detail`, y la duración `finishedAt - startedAt` en ms.

**Lógica pura en `devopsActionConsoleModel.ts`** (todo lo testeable sin DOM, por el gap RTL/jsdom):
```ts
export type ProposalBlock = '' | 'no_match' | 'ambiguous' | 'missing_params'
  | 'flag_off' | 'agent_write_disabled';

/** Texto EXACTO del botón principal según el bloqueo. Nunca vacío. */
export function primaryActionLabel(p: ProposalView): string;
/** true si el botón Ejecutar debe estar deshabilitado. */
export function isRunDisabled(p: ProposalView): boolean;
/** Mensaje que explica POR QUE no se puede ejecutar, y QUE hacer al respecto.
 *  Para 'agent_write_disabled' debe nombrar la ruta manual, no solo negar. */
export function blockedExplanation(p: ProposalView): string;
/** Chips a renderizar: siempre [accion, entorno, impacto] en ese orden. */
export function headerChips(p: ProposalView): { text: string; tone: 'ok'|'warn'|'bad'|'faint' }[];
/** Recibo -> línea legible. */
export function receiptLine(r: DevOpsActionReceipt): string;
```

Texto obligatorio para `agent_write_disabled` (no se negocia, porque es lo que evita que la flag OFF se sienta como una pared):
> «Esta acción escribe en un sistema real, y la ejecución desde el asistente está desactivada. Podés ejecutarla vos desde el panel: **Ver en el panel** te deja en la sección con los datos ya cargados.»

**Flag 3 — `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` (default OFF — categoría (B))**

- `config.py`: `os.getenv("STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", "false")`.
- `FlagSpec`: **SIN `default=`** (regla dura de §4.1), `requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED"` (estrella, no cadena — R4), `group="global"`, `env_only=False`.
  Comentario obligatorio, en la línea de la flag:
  > **EXCEPCIÓN DURA (B)** — es la única ruta por la que una frase en lenguaje natural puede terminar **escribiendo en un sistema real del operador**: dispara pipelines (`devops.pipeline.trigger`), ejecuta despliegues (`devops.deployment.execute`), publica (`devops.publication.run`, `devops.solution.publish`), commitea al repo real (`devops.pipeline_edit.commit`, vía `ado_provider.commit_file`, `backend/services/ado_provider.py:146`) y corre comandos en un servidor remoto (`devops.remote_console.run`). Precedente exacto: `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` OFF (`harness_flags.py:3166-3187`) mientras su hermana de solo-lectura `STACKY_PIPELINE_NL_EDIT_ENABLED` está ON (`:3149-3165`). **Con esta flag OFF el sistema NO pierde capacidad**: las 16 acciones de solo lectura se ejecutan igual desde el asistente, y las 7 de escritura se muestran completas con su vista previa y un botón que lleva al panel a hacerlas a mano.
- `_CATEGORY_KEYS["devops"]`, `PLAIN_HELP`, y **`_REQUIRES_MAP_FROZEN`** (`test_harness_flags_requires.py:120`). **NO** va en `_CURATED_DEFAULTS_ON` (es OFF y no declara `default`).

**Tests — `devopsActionConsoleModel.test.ts`** (9 casos)
1. `isRunDisabled` ⇒ `true` para los 5 `blocked_reason` no vacíos y `false` para `''`.
2. `primaryActionLabel` nunca devuelve `''`, para los 6 estados.
3. `blockedExplanation('agent_write_disabled')` contiene la frase `'Ver en el panel'`.
4. `blockedExplanation('missing_params')` nombra al menos un parámetro faltante.
5. `headerChips` devuelve **siempre 3 chips**, en el orden acción/entorno/impacto.
6. `headerChips` con `targets_environment:true` y `environment:''` ⇒ el chip 2 tiene `tone:'bad'`.
7. `headerChips` con `impact:'high'` ⇒ el chip 3 tiene `tone:'bad'`.
8. `receiptLine` de un recibo ok incluye `'✅'` y la duración en ms.
9. `receiptLine` de un recibo con `confirmed:false` dice explícitamente que fue cancelado por el operador.

**Comando:** desde `frontend/`: `npx vitest run src/components/devops/devopsActionConsoleModel.test.ts`; y backend: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -v` + `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -v`.
**Aceptación binaria:** 9 passed en vitest; 56 passed y 9 passed en los dos de flags; `npx tsc --noEmit` limpio; y `npx vitest run src/__tests__/devopsPollingRatchet.test.ts` sigue verde (los componentes nuevos no sondean).

**Flag:** `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` — **default OFF, categoría (B)** (razón y `archivo:línea` arriba).
**Runtimes:**
- **Codex CLI / Claude Code CLI** — la tarjeta se alimenta de `/propose` (determinista). Opcionalmente el chat existente de `devops_agent.py` sigue disponible sin cambios.
- **GitHub Copilot Pro** — **funciona completo**: catálogo, propuesta, vista previa, confirmación y ejecución de acciones de lectura. *Fallback explícito:* el chat legacy de `devops_agent.py` sigue devolviendo 400 para Copilot (no se toca, ver §8), pero la consola de acciones **no lo usa**, así que el operador de Copilot ya no queda sin camino.
**Trabajo del operador:** *opt-in (default ON)* para ver y previsualizar; para que el asistente **ejecute lo que escribe**, el operador prende una flag desde Configuración → Arnés → DevOps (un click, y es exactamente la decisión que no le queremos sacar).

---

### F7 — Recablear los botones manuales al mismo ejecutor

**Objetivo.** Que el botón de siempre y la acción del asistente sean **el mismo código**. **Valor:** cierra KPI-6; a partir de acá "coherente" deja de ser una opinión.

**Archivos a editar** (uno por vez, en este orden, verificando después de cada uno):
1. `frontend/src/components/devops/ServersSection.tsx`
2. `frontend/src/components/devops/BuildWorkshopSection.tsx`
3. `frontend/src/components/devops/PipelineBuilderSection.tsx`
4. `frontend/src/components/devops/ProductionFlow.tsx`
5. `frontend/src/components/devops/RemoteConsoleSection.tsx`
6. `frontend/src/components/devops/SolutionPublisherSection.tsx`

**Transformación exacta, idéntica en los 6** (ejemplo con `ServersSection.tsx`):

```diff
-const ok = await askConfirm({
-  title: 'Ejecutar en el servidor',
-  message: `Vas a correr esto en ${alias}.`,
-  confirmLabel: 'Ejecutar',
-  tone: 'danger',
-});
-if (!ok) return;
-await DevOpsServers.runCommand(alias, cmd);
+const receipt = await runDevOpsAction(
+  actionMeta('devops.remote_console.run'),
+  { project, environment: env, server_alias: alias, command: cmd },
+  bindingFor('devops.remote_console.run'),
+  { askConfirm, navigate, now: () => Date.now(), onReceipt: setLastReceipt },
+);
+if (!receipt.ok) return;
```

**Reglas duras del recableado:**
- **No se borra ningún botón.** El operador ve exactamente los mismos controles.
- **El texto de la confirmación cambia** (ahora lo genera `confirmRequestFor`), pero **el `tone` no puede aflojarse**: si hoy una confirmación es `'danger'`, su acción debe declarar `impact:'high'` en el catálogo. Verificar acción por acción antes de editar.
- Si una sección tiene una acción con efecto que **no** está en el catálogo, se agrega al catálogo en esta fase (F0 quedó con 23; F7 puede llegar a más) — **nunca** se deja fuera.
- Si un binding no puede reproducir exactamente el comportamiento del botón, **se detiene la fase y se reporta**; no se aproxima.

**Test — `frontend/src/__tests__/plan266Adoption.test.ts`** (patrón calcado de `plan175Adoption.test.ts`, que ya existe)
1. Los 6 archivos de la lista **importan** `runDevOpsAction` desde `../../services/devopsActionRunner`.
2. Ninguno de los 6 contiene la cadena `askConfirm({` (construcción de `ConfirmRequest` a mano).
3. `frontend/src/services/devopsActionRunner.ts` es el **único** archivo de `src/` (fuera de tests) que contiene `confirmRequestFor` como definición.

**Comando:** desde `frontend/`: `npx vitest run src/__tests__/plan266Adoption.test.ts` + `npx tsc --noEmit`
**Aceptación binaria:** 3 passed, `tsc` sin errores, y `npx vitest run src/__tests__/uiDebtRatchet.test.ts` y `npx vitest run src/__tests__/undoConfirmRatchet.test.ts` siguen verdes (los ratchets de deuda del 239/175 no empeoran).

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED`. **Nota de degradación:** los bindings y `runDevOpsAction` funcionan con el catálogo **embebido en el frontend como fallback** si el `GET /catalog` falla o la flag está OFF, para que apagar la flag **nunca** rompa un botón que hoy funciona. El fallback embebido se genera copiando los metadatos de las acciones de las 6 secciones tocadas (no las 23) — se declara en `devopsActionBindings.ts` como `FALLBACK_META: Record<string, DevOpsActionMeta>` y un test verifica que sus 6+ entradas coinciden campo a campo con el catálogo backend.
**Runtimes:** irrelevante (UI). Idéntico en los 3.
**Trabajo del operador: ninguno.** Los mismos botones, en el mismo lugar, con el mismo efecto.

---

### F8 — Ratchet anti-deriva y cierre

**Objetivo.** Que **no pueda** nacer una acción DevOps fuera del catálogo. **Valor:** convierte la coherencia en un test, que es lo único que sobrevive a los próximos 20 planes.

**Archivos a crear**
- `backend/tests/test_devops_action_ratchet.py`
- `frontend/src/__tests__/devopsActionCatalogRatchet.test.ts`

**`backend/tests/test_devops_action_ratchet.py`** (reglas estructurales sobre el catálogo)
1. `test_write_declara_impacto` — toda acción con `effect=="write"` tiene `impact != "none"`.
2. `test_targets_environment_exige_param_environment` — si `targets_environment` es `True`, existe un `ActionParam` llamado `environment`, de `type=="enum"`, con `required=True` y `enum_values` no vacío.
3. `test_environment_implica_targets` — la recíproca: si hay un param `environment`, `targets_environment` debe ser `True`.
4. `test_read_no_tiene_impacto_alto` — `effect=="read"` ⇒ `impact == "none"`.
5. `test_write_tiene_flag_key` — toda acción `write` declara `flag_key != ""` (nada que escriba puede quedar sin flag).
6. `test_health_key_existe_en_health_payload` — todo `health_key != ""` es una key real de `api.devops._health_payload()`.
7. `test_flag_key_existe_en_el_registro` — todo `flag_key != ""` está en `{s.key for s in FLAG_REGISTRY}`.
8. `test_section_ids_espejan_el_tsx` — leer `frontend/src/pages/DevOpsPage.tsx` como TEXTO, extraer los ids con `re.findall(r"^\s*id: '([a-z0-9-]+)',", src, re.M)`, y afirmar `set(...) == set(DEVOPS_SECTION_IDS)`. **Esta es la guarda contra el drift más caro**: si alguien agrega una sección DevOps y no la declara acá, el test lo caza.
9. `test_nav_path_de_seccion_es_devops_slug` — si `section_id` no es `None`, `nav_path == f"/devops/{section_id}"`.
10. `test_ninguna_accion_escribe_sin_confirmacion_posible` — para toda `write`, `summary` no está vacío (la tarjeta lo necesita para explicar qué va a pasar).

**`frontend/src/__tests__/devopsActionCatalogRatchet.test.ts`** (paridad backend↔frontend, leyendo el `.py` como texto — patrón calcado de `devopsPollingRatchet.test.ts:17-21`)
```ts
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { DEVOPS_ACTION_BINDINGS } from '../services/devopsActionBindings';

const CATALOG_PY = path.resolve(__dirname, '../../../backend/services/devops_action_catalog.py');

function catalogIds(): string[] {
  const src = fs.readFileSync(CATALOG_PY, 'utf8');
  return [...src.matchAll(/^\s*id="(devops\.[a-z_]+\.[a-z_]+)"/gm)].map((m) => m[1]);
}
```
1. `test_todo_id_del_catalogo_tiene_binding` — `catalogIds()` ⊆ `Object.keys(DEVOPS_ACTION_BINDINGS)`; el mensaje de fallo **lista los ids huérfanos por nombre**.
2. `test_todo_binding_tiene_id_en_el_catalogo` — la inclusión inversa; el mensaje lista los bindings fantasma.
3. `test_igualdad_exacta` — los dos conjuntos ordenados son iguales (KPI-7).
4. `test_el_archivo_de_catalogo_existe` — falla con un mensaje explícito si la ruta se rompió (protege contra un falso verde por regex que no matchea nada sobre un archivo movido: si el `.py` no existe, el test **no** puede pasar con listas vacías).
5. `test_hay_al_menos_23_ids` — protege contra el mismo falso verde: una regex que deja de matchear daría 2 listas vacías **iguales**, y `test_igualdad_exacta` pasaría sin decir nada.

**Registro:** `tests/test_devops_action_ratchet.py` en `HARNESS_TEST_FILES` (`.sh` y `.ps1`).

**Comandos:**
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v`
- desde `frontend/`: `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_ratchet_meta.py -v`

**Aceptación binaria:** 10 passed (backend) + 5 passed (frontend) + 4 passed (meta-ratchet).

**Flag:** ninguna (son tests).
**Runtimes:** irrelevante.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta) |
|---|--------|--------------|------------------------|
| R1 | El recableado de F7 cambia el comportamiento de un botón que hoy funciona | Media | F7 se hace **un archivo por vez**; regla dura "el `tone` no puede aflojarse"; `FALLBACK_META` embebido para que la flag OFF nunca rompa un botón; `plan266Adoption.test.ts` verifica la adopción y `tsc --noEmit` la compilación |
| R2 | El ratchet frontend da **falso verde** si la regex deja de matchear (archivo movido o formato cambiado) | Alta si no se previene | Tests 4 y 5 del ratchet: existencia del archivo + mínimo de 23 ids. Dos listas vacías iguales ya no pasan |
| R3 | El matcher determinista confunde dos acciones y propone la equivocada | Media | `is_ambiguous` + `blocked_reason == "ambiguous"` deshabilita `[Ejecutar]` y ofrece elegir. Además `MIN_SCORE = 0.6` y `needs_confirmation` obligatorio para `write` |
| R4 | Una flag queda mal cableada y rompe tests ajenos | Alta (histórico) | §4.1: las 7 patas tabuladas, la regla "OFF no declara `default=False`", la regla R4 de la estrella, y el comando de verificación por flag |
| R5 | `test_harness_flags_help.py` sale rojo | Certeza parcial (4 fallos ajenos preexistentes) | Verificar que las 3 keys nuevas **no** estén entre las ofensoras; los textos de `PLAIN_HELP` ya fueron chequeados contra la denylist de `:17-20` |
| R6 | La paleta introduce un sondeo y rompe el ratchet del 239 F6 | Baja | El catálogo se pide **una vez al abrir**, nunca en intervalo; `devopsPollingRatchet.test.ts` es criterio de aceptación de F5 y F6 |
| R7 | Colisión de merge con 264 (modelo/effort) o 265 (consola) | Media | §8 declara la frontera archivo por archivo; el 266 **no toca** `model_catalog.py`, `llm_router.py`, `ModelEffortPicker.tsx`, `CodexConsoleDock.tsx` ni `store/workbench.ts` |
| R8 | Un modelo menor implementa `runDevOpsAction` con el orden de guardas invertido y ejecuta sin confirmar | Media | El orden de los 5 pasos está escrito literalmente en el docstring de F4, y los tests 7/8/11 lo verifican con spies de 0 llamadas |
| R9 | `sqlite` bajo pytest da `SQLITE_LOCKED` en los tests de API | Alta (conocido) | `test_devops_actions_api.py` **no escribe en la DB**: `/catalog`, `/propose` y `/preview` son de solo lectura. Si aun así aparece flaky, correr el archivo 8-12 veces y confirmar |
| R10 | Se agrega una sección DevOps nueva y `DEVOPS_SECTION_IDS` queda stale | Alta a mediano plazo | `test_section_ids_espejan_el_tsx` (F8, test 8) lee el `.tsx` real |

---

## 7. Fuera de scope (declarado, no escondido)

1. **Rediseño de shell, navegación, grupos, tokens o barrido de estilos inline.** Es el plan 239, ya implementado. El 266 no edita `devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, `DevOpsTabsV2.tsx` ni `DevOpsHeaderV2.tsx`.
2. **El checklist visual de 10 puntos del 239 F8.** Sigue requiriendo navegador; RTL y jsdom no están en el `package.json` del frontend. El 266 **reduce** su superficie (la coherencia de acciones pasa a ser verificable por test) pero no lo cierra.
3. **Eliminar el chat de texto libre de `api/devops_agent.py`.** Se deja intacto, incluido su 400 para Copilot (`:69-78`). Removerlo es un plan aparte, con su propia migración.
4. **Endpoints de ejecución nuevos en el backend.** El 266 declara y confirma; ejecuta reusando lo que ya existe. Un endpoint `POST /devops/actions/execute` sería una segunda implementación de 23 operaciones — exactamente lo que este plan combate.
5. **Ejecución multi-paso / encadenada** ("desplegá y después corré los smoke tests"). Una propuesta = una acción. El encadenamiento es un plan posterior, y necesitaría su propio contrato de HITL por paso.
6. **Enriquecimiento por LLM de la propuesta** (mejorar `what_will_happen` o inferir parámetros con un modelo). El seam está listo (`describe()` es reemplazable y `PreflightRuntimeUnavailable` es el fallback), pero el 266 entrega **solo el camino determinista**, que es el que da paridad de 3 runtimes.
7. **Persistir un historial de recibos.** Los recibos se muestran en sesión. Persistirlos es del eje de telemetría (plan 171).
8. **Traducir el catálogo a otros idiomas.** Todo en español rioplatense, como el resto del producto.

---

## 8. Frontera de merge y convivencia con 239, 264 y 265

| Plan | Archivos que ESE plan posee | Qué hace el 266 con ellos |
|------|------------------------------|----------------------------|
| **239** (IMPLEMENTADO) | `pages/devopsCockpitShell.ts`, `pages/DevOpsCockpitNav.tsx`, `pages/DevOpsTabsV2.tsx`, `pages/DevOpsHeaderV2.tsx`, `services/devops_overview.py`, `components/devops/DevOpsOverviewSection.tsx`, `__tests__/devopsPollingRatchet.test.ts` | **Lectura solamente.** El 266 consume `DevOpsSection.id` y `nav_path=/devops/<id>`, y agrega la acción `devops.overview.refresh` que llama al `GET /api/devops/overview` existente. **Cero ediciones.** `devopsPollingRatchet.test.ts` es criterio de aceptación de F5 y F6 |
| **264** (CRITICADO v2, sin implementar) | `services/model_catalog.py`, `services/llm_router.py` (`clamp_model` `:38`, `clamp_effort_for_model` `:60`), `components/ModelEffortPicker.tsx`, `effort_mode:"no_aplica"` para Copilot, y el fix de `agent_runner.py:256-264` | **Cero ediciones.** El 266 **no** toca el eje modelo/effort porque su camino es determinista. Si más adelante se agrega enriquecimiento por LLM (fuera de scope, §7.6), debe usar `clamp_model`/`clamp_effort_for_model` del 264 y **nunca** el literal `_EFFORTS` de `devops_agent.py:15` |
| **265** (PROPUESTO v1) | `components/CodexConsoleDock.tsx`, `store/workbench.ts:10-11`, `hooks/useExecutionStream.ts` | **Cero ediciones.** Único punto de contacto potencial: si el 265 agrega comandos a la paleta, ambos planes editan `commandPaletteData.ts`. **Regla de convivencia:** el 266 agrega `"devops-action"` **al final** del union `CommandKind` y una función nueva `devopsActionCommands()`; no reordena `CommandKind` ni modifica `NAV_COMMANDS`, `fuzzyScore` ni `mergeDeepResults`. Un merge posterior es aditivo por construcción. **Ojo con el duplicado silencioso**: si ambas ramas agregan una entrada a `DEEP_ICONS`, git puede fusionar sin conflicto — verificar `tsc --noEmit` después del merge |
| **175** (implementado) | `services/entityActions.ts`, `services/confirmGateway.ts` | `confirmGateway.ts` se **importa sin modificar**. `entityActions.ts` se toca **solo** si se decide exportar `EntityKind` ampliado — **no hace falta**: `devops-action` vive en su propio módulo y `EntityKind` usa `Extract<>`, que ignora los valores nuevos del union |
| **129** (implementado) | `components/commandPaletteData.ts`, `components/CommandPalette.tsx` | Edición **aditiva** (F5), con test de no-regresión de `fuzzyScore` |
| **41** (implementado) | `services/intent_preflight.py` | **Lectura solamente**: se calca la forma de `IntentBrief`. No se importa ni se modifica |
| **250** (implementado) | `api/pipeline_editor.py`, `components/devops/PipelineEditNlPanel.tsx`, sus 2 flags | **Cero ediciones.** El catálogo declara `devops.pipeline_edit.preview` y `devops.pipeline_edit.commit` apuntando a las flags **existentes** del 250. Su patrón ON/OFF es el precedente citado para la flag 3 |

---

## 9. Glosario

- **Acción** — una operación nombrable del panel DevOps, declarada una sola vez en `DEVOPS_ACTION_CATALOG`.
- **Catálogo** — `backend/services/devops_action_catalog.py`. Fuente de verdad de la **identidad y la seguridad** de una acción (qué es, dónde vive, si escribe, qué impacto tiene, qué flag la gatea, cómo se pide en español).
- **Binding** — `frontend/src/services/devopsActionBindings.ts`. Fuente de verdad del **cómo se hace**, reusando endpoints existentes.
- **Superficie** — un lugar desde donde el operador dispara una acción. Son tres: botón manual, paleta, asistente.
- **`ActionProposal`** — lo que el asistente devuelve en vez de prosa. Calca `IntentBrief` (plan 41).
- **Recibo (`DevOpsActionReceipt`)** — el resultado visible de una acción: ok/error, resumen, detalle, duración, si fue confirmada.
- **`effect`** — `read` (no cambia nada) o `write` (escribe en un sistema real). Determina si se confirma.
- **`impact`** — `none` / `low` / `high`. Determina el `tone` de la confirmación.
- **`targets_environment`** — si la acción actúa sobre un entorno concreto del operador. Obliga a declarar el param `environment`.
- **Ratchet** — test que solo permite mejorar: impide que nazca una acción fuera del catálogo o que el catálogo y los bindings diverjan.
- **Las 7 patas** — los 7 lugares donde se cablea una flag del arnés (§4.1).

---

## 10. Orden de implementación

1. **F0** — `devops_action_catalog.py` + catálogo de 23 acciones + flag `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (7 patas) + `test_devops_action_catalog.py` (15 tests).
2. **F1** — `api/devops_actions.py` con `GET /catalog` + 3 keys nuevas en `_health_payload()` + los 3 atributos en `config.py` + `test_devops_actions_api.py` (5 tests).
3. **F2** — `devops_action_matcher.py` + `test_devops_action_matcher.py` (12 tests).
4. **F3** — `devops_action_proposal.py` + `POST /propose` + `POST /preview` + flag `STACKY_DEVOPS_ACTION_NL_ENABLED` (7 patas, incluye `_REQUIRES_MAP_FROZEN`) + 12 tests más en `test_devops_actions_api.py`.
5. **F4** — `devopsActionTypes.ts` + `devopsActionRunner.ts` + `devopsActionBindings.ts` + 14 tests de vitest.
6. **F5** — `commandPaletteData.ts` (aditivo) + `CommandPalette.tsx` + `commandPaletteDevopsActions.test.ts` (7 tests).
7. **F6** — `devopsActionConsoleModel.ts` + `DevOpsActionProposalCard.tsx` + `DevOpsActionConsole.tsx` + `DevOpsAgentSection.tsx` + flag `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` (default **OFF**, 7 patas) + 9 tests.
8. **F7** — recableado de los 6 archivos de secciones, **uno por vez** + `plan266Adoption.test.ts` (3 tests).
9. **F8** — `test_devops_action_ratchet.py` (10 tests) + `devopsActionCatalogRatchet.test.ts` (5 tests).

Registrar en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh:20` **y** `backend/scripts/run_harness_tests.ps1:15`) los 4 archivos backend nuevos: `tests/test_devops_action_catalog.py`, `tests/test_devops_actions_api.py`, `tests/test_devops_action_matcher.py`, `tests/test_devops_action_ratchet.py`.

---

## 11. Definition of Done global

Todos estos comandos, corridos **por archivo** desde la raíz `Stacky Agents` (backend) o desde `frontend/` (vitest), en verde:

```
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_catalog.py -v      # 15 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_matcher.py -v      # 12 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v         # 17 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v      # 10 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -v              # 56 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -v     #  9 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_ratchet_meta.py -v       #  4 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops.py -v                     # sin regresion
```
```
npx vitest run src/services/devopsActionRunner.test.ts                       # 11 passed
npx vitest run src/services/devopsActionBindings.test.ts                     #  3 passed
npx vitest run src/components/devops/devopsActionConsoleModel.test.ts        #  9 passed
npx vitest run src/components/__tests__/commandPaletteDevopsActions.test.ts  #  7 passed
npx vitest run src/components/__tests__/commandPaletteData.test.ts           # sin regresion
npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts              #  5 passed
npx vitest run src/__tests__/plan266Adoption.test.ts                         #  3 passed
npx vitest run src/__tests__/devopsPollingRatchet.test.ts                    # sin regresion
npx vitest run src/__tests__/uiDebtRatchet.test.ts                           # sin regresion
npx vitest run src/services/entityActions.test.ts                            # sin regresion
npx tsc --noEmit                                                             # 0 errores
```

Y estos criterios cualitativos, verificables leyendo el diff:

- [ ] Ningún archivo de los planes 239, 264 y 265 listados en §8 fue editado.
- [ ] Las 3 flags nuevas tienen sus 7 patas cableadas, y la OFF **no** declara `default=False`.
- [ ] La flag OFF tiene escrita, en su propia línea, la categoría de excepción **(B)** y el porqué con `archivo:línea`.
- [ ] Ningún `setInterval`, `setTimeout` recurrente ni `refetchInterval` nuevo.
- [ ] Ningún endpoint de ejecución nuevo en el backend.
- [ ] Ningún botón existente del panel DevOps fue borrado.
- [ ] Con las 3 flags apagadas, el panel se comporta igual que antes del plan.
