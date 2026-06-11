# 21 — Plan de Hardening del Arnés Multi-Proveedor — Stacky Agents

Fecha: 2026-06-10 · Branch base: `feat/memoria-colaborativa-hardening`
Sucede y amplía a `PLAN-ROBUSTECIMIENTO-ARNES.md` (raíz del repo, 2026-06-09), cuyas Fases 1-3 ya están **implementadas** para el runtime `claude_code_cli` (flags OFF). Este plan generaliza el arnés a TODOS los runtimes/proveedores.

**Principio rector**: usar Stacky Agents tiene que dar un valor agregado enorme contra usar el CLI pelado, sin importar qué proveedor corre debajo. El arnés es una capa PROPIA de Stacky (contexto curado + validación + autocorrección + memoria + skills + telemetría), con adaptadores finitos por proveedor.

---

## 0. Cómo usar este documento (leer ANTES de tocar código)

Este plan está escrito para ser ejecutado por un desarrollador agéntico sin acceso a la conversación que lo originó. Reglas de oro:

1. **No inventes rutas ni APIs.** Toda ruta/línea citada acá fue verificada el 2026-06-10. Si una línea se movió, buscá el símbolo con grep antes de editar.
2. **Tests por archivo, nunca la suite completa como gate.** La suite completa del backend está contaminada históricamente (~40 fails / ~449 errors incluso en HEAD limpio). Validá así:
   ```powershell
   cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
   python -m pytest tests/test_<archivo>.py -q
   ```
   Si tocás un contrato compartido, compará contra baseline: `git stash` → correr los mismos archivos → `git stash pop`.
3. **PowerShell 5.1**: no existe `&&`; usar `;` o `if ($?)`. Encoding UTF-8 explícito al escribir archivos desde scripts.
4. **`.gitignore:43` ignora `Stacky Agents/backend/Stacky/*`**: los `.agent.md` NO se versionan (el runtime los lee de `backend/Stacky/agents/`, no de `DeployStackyAgents`). Cualquier carpeta nueva bajo `backend/Stacky/` (p.ej. `skills/`) queda gitignored salvo regla de negación explícita.
5. **DB viva en `Stacky Agents/DeployStackyAgents/data`** (producción del operador). En desarrollo la DB es `backend/data/stacky_agents.db` (`config.py:58`). Jamás apuntar tests a la DB del deploy.
6. **Mono-operador, sin auth real**: `current_user` es un header sin validar. No construir RBAC ni "permisos" que aparenten seguridad.
7. **Decisiones vinculantes del operador (2026-06-09), NO revertir ni re-discutir**:
   - Sin wrapper PowerShell alrededor de los CLIs (`PLAN-ROBUSTECIMIENTO-ARNES.md §5.1`).
   - Cap duro de modelo en el path Claude: jamás Opus/Fable, ni por override (`llm_router.clamp_model`, `services/llm_router.py:33`).
   - `--dangerously-skip-permissions` SIEMPRE activo en el CLI Claude (`config.py:148-150`); allowlists de tools descartadas como default.
8. **Sin fallback silencioso entre runtimes** (`agent_runner.py:114-121`). Un error de un runner es un error real.
9. **Todo flag nuevo nace OFF por default**, patrón master global + allowlist CSV de proyectos, con helper en `services/cli_feature_flags.py` (dueño único de esa decisión).
10. **TDD**: cada ítem indica el test a escribir primero. Escribilo, verificá que falla por la razón correcta, implementá lo mínimo, verificá verde.

---

## 1. Inventario verificado del arnés actual (rutas:líneas)

### 1.1 Dispatch y runtimes

Tres runtimes seleccionables por el operador (`frontend/src/components/AgentRuntimeSelector.tsx`):

- **Dispatch**: `backend/agent_runner.py:44-256` — `github_copilot` (default), `codex_cli`, `claude_code_cli`. Sin fallback (`:114-121`).
- **`github_copilot`** (one-shot, no agéntico): pipeline completo en `agent_runner.py:493-819` — enrich → PII → cache → router → **egress** (`:651`) → system prompt FA-* (`agents/base.py:56-159`: few-shot FA-12, anti-patterns FA-11, decisions FA-13, constraints FA-08, style FA-10) → invoke (`copilot_bridge.py:131-162`, backends `mock`/`vscode_bridge`/`copilot`) → **contract_validator** (`:688`) → **confidence** (`:696`) → cache/webhooks/audit/embeddings → post_run_memory.
- **`claude_code_cli`** (agéntico, el más arnesado tras Fases 1-3): `services/claude_code_cli_runner.py` (1642 líneas) — enrich (`:363`), MCP `--mcp-config` (`:459-476`), resume+delta (`:478-491`, `_resolve_resume :1153`), router+clamp (`:493-509`), spawn, telemetría stream F1.2 (`:602`, persistida `:714-724`), autocorrección stdin F1.3 (`:608`, `services/cli_autocorrect.py:65 AutocorrectLoop`), hooks F1.4 (`services/claude_cli_hooks.py:85 write_run_settings` → `POST /api/agents/validate-artifact`, `api/agents.py:33`), contract+confidence post-run F1.1 (`:1075-1076`), `_build_command` (`:905-954`), reglas de output `_STACKY_RULES` (`:1112`), `_build_system_prompt` (`:1238`).
- **`codex_cli`** (agéntico, casi sin arnés): `services/codex_cli_runner.py` (1206 líneas) — enrich (`:287`), PII (`:303`), prompt propio `_build_codex_prompt` (`:732`) + materialización de agentes (`:797`), `_build_command` (`:605-637`: `codex exec --json -s <sandbox> [-m modelo estático] -`), captura de `session_id` (`:856-965`), resume para input del operador (`:193-211`, `_build_resume_command :639`, `_input_resume_context :976`). **NO tiene**: contract_validator (0 hits), confidence, artifact gate, autocorrección, hooks, MCP, router/clamp, telemetría de costo, conocimiento de proyecto, repro script.

### 1.2 Seams agnósticos ya existentes (la base de este plan)

| Pieza | Ruta | Usada por |
|---|---|---|
| Enriquecimiento de contexto (épica, artifacts, similares, comentarios ADO, client profile, memoria) | `services/context_enrichment.py:34 enrich_blocks` | los 3 runtimes |
| Presupuesto de contexto F2.4 (ranking + truncado) | `context_enrichment.py:140 _apply_context_budget` | los 3 (flag) |
| Memoria colaborativa (inyección user-prompt) | `context_enrichment.py:338`, `services/memory_store.py:852 get_context_for_run` | los 3 (doble flag OFF) |
| Validación de contrato por tipo de agente | `contract_validator.py:130 validate` (`_CONTRACTS :50`) | copilot + claude |
| Confidence score | `services/confidence.py` | copilot + claude |
| Validación de artifacts (pending-task.json / comment.html, id real vs ordinal) | `services/artifact_validator.py:136,:220,:257` | claude (hooks+autocorrect) + `output_watcher` |
| Flags por proyecto (master AND allowlist CSV) | `services/cli_feature_flags.py:25 project_enabled` + helpers `:47-102` | claude |
| MCP tools (lógica separada del protocolo) | `services/stacky_mcp_tools.py:42-227` (`stacky_get_ticket/search_memory/search_similar/submit_comment/submit_task`), server JSON-RPC stdio a mano `services/stacky_mcp_server.py`, config efímera `services/stacky_mcp.py:22` | claude |
| Router + cap duro de modelo | `services/llm_router.py:174 decide`, `:33 clamp_model` | copilot + claude |
| Conocimiento de proyecto para system prompt CLI (anti-patterns/decisions/constraints/glossary) | `services/cli_project_knowledge.py:34` | claude (flag) |
| Salud del arnés | `services/harness_health.py:74 compute_health` + `GET /api/metrics/harness-health` (`api/metrics.py:221`) | **solo** runtime claude_code_cli |
| Evals golden-set (juez = contract_validator, sin LLM) | `backend/evals/golden_runner.py`, sets en `evals/agents/{functional,qa}` | CLI `python -m evals run <agent>|all` |
| Red de seguridad de outputs | `services/output_watcher.py` (polling fallback), `services/agent_completion.py` (gateway, modo shadow), `services/ado_write_outbox.py` ("solo Stacky escribe ADO") | los 3 |
| Captura post-run de memoria | `services/post_run_memory.py` (`_CAPTURE_TYPE="session_summary" :44`) | los 3 |

### 1.3 Qué es frágil, duplicado o teatro (verificado)

1. **Asimetría codex_cli** — el segundo runtime agéntico no tiene NADA del arnés de calidad (ver §1.1). Es el gap individual más grande.
2. **Todo OFF** — `config.py:151-224`: contract gate, autocorrect, hooks, knowledge, resume, MCP, budget, memoria: todos `false`. Valor ya pagado que no se entrega.
3. **Texto del contrato de outputs duplicado** — `_STACKY_RULES` (`claude_code_cli_runner.py:1112`) vs `_build_codex_prompt` (`codex_cli_runner.py:732`): dos fuentes para las mismas reglas (file-drop, nombres, ADO id real). Divergen en silencio.
4. **Conocimiento con 3 canales y dueño "por convención"** — FA-* system prompt (solo copilot), `cli_project_knowledge` (solo claude), memoria colaborativa (user prompt, los 3). La no-duplicación depende de convención (`post_run_memory` captura solo `session_summary`), no de estructura: `memory_store.search`/`get_context_for_run` no filtran por tipo y `POST /api/memory` acepta tipo libre.
5. **`harness_health` mono-runtime** — agrega solo `runtime=claude_code_cli`; codex y copilot invisibles al dashboard.
6. **Evals anémicos** — 3 casos (functional, qa); developer/technical sin gate. Editar un `.agent.md` se prueba en producción.
7. **Sin guard de runaway in-run** — `CLAUDE_CODE_CLI_TIMEOUT=0` (ilimitado) y nadie mira `num_turns`/costo durante el run.
8. **Hazard `_resolve_cwd`** — `claude_code_cli_runner.py:1504`: si `workspace_root` es inválido cae en silencio al dir de instalación de Stacky, con skip-permissions ON (el agente opera sobre la instalación).
9. **Teatro conocido (no construir encima)**: `STACKY_AGENT_TOKEN`/`current_user` sin sustrato de auth; `egress_policies` solo corre en copilot.

---

## 2. Matriz de paridad por runtime (estado actual)

| Capacidad del arnés | github_copilot | codex_cli | claude_code_cli |
|---|---|---|---|
| Contexto enriquecido + PII + budget + memoria | SÍ | SÍ | SÍ |
| Conocimiento de proyecto en system prompt | SÍ (FA-*, `base.py`) | **NO** | SÍ (flag, `cli_project_knowledge`) |
| Validación de contrato + confidence | SÍ | **NO** | SÍ (flag gate) |
| Validación de artifacts en origen (hooks/autocorrección) | n/a (no escribe archivos) | **NO** | SÍ (flags) |
| Tools gobernadas (MCP submit_* → outbox ADO) | n/a | **NO** | SÍ (flag) |
| Router de modelo + cap | SÍ | **NO** (modelo estático `config.CODEX_CLI_MODEL`) | SÍ |
| Telemetría tokens/costo/turnos | parcial | **NO** (solo session_id) | SÍ |
| Resume de sesión en re-run | n/a | parcial (solo input del operador) | SÍ (flag) |
| Egress policies | SÍ | **NO** | **NO** |
| Salud del arnés (dashboard) | **NO** | **NO** | SÍ |
| Evals/golden gate | parcial (2 agentes) | parcial | parcial |
| Guard de runaway (turnos/costo) | n/a | **NO** | **NO** |
| Skills/procedimientos reutilizables | **NO** | **NO** | **NO** |

---

## 3. Gap analysis contra el estado del arte de arneses agénticos

Comparación contra lo que ofrecen los mejores arneses (Claude Code, Codex CLI, agentes con harness propio). Columna clave: "¿riesgo de empeorar?" — el pedido explícito es agregar lo que falta SIN hacerlo peor.

| # | Capacidad (estado del arte) | Stacky hoy | ¿Aplica? | Valor vs CLI pelado | Riesgo de empeorar / mitigación |
|---|---|---|---|---|---|
| G1 | Verificación automática post-run (gates de contrato/artifacts) | Solo copilot+claude; codex sin nada | SÍ — es EL diferencial | Altísimo: el CLI pelado no sabe qué es un output válido para ADO | Bajo. Gate con flag OFF; status `needs_review`, nunca descarta trabajo |
| G2 | Feedback in-run al agente (hooks post-tool-use, autocorrección) | Solo claude | SÍ (codex vía `exec resume`) | Altísimo: convierte "crea archivos pero no la task" en run exitoso | Medio si se abusa: cap de reintentos (ya existe patrón `AUTOCORRECT_MAX_RETRIES=2`) |
| G3 | Tools con schema validado (structured outputs) en vez de convención de archivos | MCP solo claude (flag) | SÍ | Altísimo: imposible entregar JSON inválido; acceso gobernado a ADO sin credenciales | Bajo: file-drop + output_watcher quedan de fallback |
| G4 | Skills / conocimiento procedimental reutilizable | NO existe | SÍ, como capa PROPIA (no `.claude/skills` provider-specific) | Alto: procedimientos del cliente (formato plan de pruebas, convenciones) que el CLI pelado no tiene | Medio: riesgo de doble inyección con memoria/FA-* → tabla de ownership obligatoria (§H4.4) |
| G5 | Memoria persistente | Implementada (Fases A-E), OFF | SÍ — activar y medir | Alto | Medio: doble canal B5/B6 → encendido por proyecto + métricas de hit-rate ya persistidas |
| G6 | Telemetría de tokens/costo | Solo claude | SÍ | Medio-alto (decisiones de routing con costo real) | Nulo (solo metadata) |
| G7 | Resume/checkpointing de runs | claude (flag), codex parcial | SÍ | Alto (re-runs baratos y con memoria de sesión) | Bajo: flag por proyecto |
| G8 | Presupuesto/curado de contexto | Implementado, OFF | SÍ — activar | Alto (menos tokens, mejor señal) | Bajo: bloques epic/client-profile nunca se recortan |
| G9 | Evals de calidad por agente | Anémico (3 casos) | SÍ | Alto (editar prompts sin romper producción) | Bajo: gate ADVIERTE, no bloquea |
| G10 | Guard de runaway (turnos/costo in-run) | NO | SÍ | Medio (protege la billetera) | Medio: límite mal calibrado mata runs buenos → default generoso + needs_review, nunca descartar |
| G11 | Telemetría de salud del arnés multi-runtime | Solo claude | SÍ | Medio (sin medición no hay mejora) | Nulo |
| G12 | Subagentes / orquestación multi-agente | NO | **NO por default** | Bajo: los CLIs agénticos ya traen subagentes nativos; duplicarlo en Stacky quema tokens | ALTO — explícitamente NO hacer (§8) |
| G13 | Sandboxing / permisos por tool | Descartado (decisión vinculante §5.3 plan previo) | **NO** | — | ALTO (fricción) — NO hacer |
| G14 | RBAC / multiusuario | Teatro actual | **NO** (sin sustrato de auth) | — | ALTO — NO hacer |
| G15 | Contexto de proyecto tipo CLAUDE.md por workspace | Cubierto distinto: system prompt + knowledge + MCP | Parcial | Bajo marginal: duplicaría canales | Alto (doble inyección) — NO agregar canal nuevo; el equivalente Stacky es `cli_project_knowledge` + MCP |
| G16 | Plantillas de agente (packs) | Existe `backend/packs/definitions.py` | Ya cubierto | — | No tocar en este plan |

---

## 4. Arquitectura objetivo: Stacky Harness Core

**Idea central**: extraer el arnés ya probado en `claude_code_cli_runner` a un paquete agnóstico `backend/harness/`, y que cada runner sea un ADAPTADOR fino que declara sus capacidades. Nada de frameworks: es MOVER código probado, no reescribirlo.

```
backend/harness/
  __init__.py
  capabilities.py    # qué puede cada runtime (declarativo)
  post_run.py        # pipeline único: contrato + confidence + artifacts + status
  run_contract.py    # texto canónico de reglas de output (dueño único)
  telemetry.py       # contrato único de telemetría + persistencia
  model_policy.py    # caps de modelo por proveedor (reusa llm_router.clamp_model)
  runaway_guard.py   # límites in-run de turnos/costo
  resume.py          # decisión de resume + delta (compartida)
```

Contratos (firmas exactas):

```python
# harness/capabilities.py
from dataclasses import dataclass

@dataclass(frozen=True)
class RuntimeCapabilities:
    name: str                      # "github_copilot" | "codex_cli" | "claude_code_cli"
    agentic: bool                  # ejecuta tools en la máquina del operador
    writes_artifacts: bool         # produce file-drop en Agentes/outputs
    feedback_channel: str | None   # "stdin" | "resume" | None  (autocorrección)
    supports_hooks: bool
    supports_mcp: bool
    supports_session_resume: bool
    supports_model_flag: bool
    emits_cost_telemetry: bool

CAPABILITIES: dict[str, RuntimeCapabilities] = { ... }  # los 3 runtimes, sin default
```

```python
# harness/post_run.py
from dataclasses import dataclass, field

@dataclass
class PostRunResult:
    contract: "ContractResult | None"
    confidence: float | None
    artifacts: "ArtifactsReport | None"
    status_suggestion: str          # "completed" | "needs_review"
    metadata_patch: dict = field(default_factory=dict)

def finalize_run(
    *,
    runtime: str,
    agent_type: str,
    output_text: str,
    ado_id: int | None,
    gate_enabled: bool,
    log=None,
) -> PostRunResult: ...
```

```python
# harness/telemetry.py
@dataclass
class RunTelemetry:
    session_id: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    total_cost_usd: float | None = None
    num_turns: int | None = None
    raw: dict | None = None        # evento crudo si el schema del proveedor es desconocido

def persist(execution_id: int, t: RunTelemetry) -> None  # metadata["harness_telemetry"]
```

Reglas del Core:
- `harness/` NO importa runners; los runners importan `harness/`.
- Cada función del Core es pura o toca DB por los services existentes — sin estado global nuevo.
- El comportamiento del runtime claude tras la extracción debe ser BIT-IDÉNTICO (tests existentes en verde sin modificarlos, salvo imports).

---

## 5. Plan por fases (H0…H8)

Convención: fases `H*` para no colisionar con las `F*` del plan previo (ya implementadas). Cada ítem tiene: objetivo, archivos, contrato, TDD, aceptación, trampas.

### H0 — Activar lo ya construido y medirlo (quick-wins ≤1 día; H0.4 ~1-2 días) — SIN CÓDIGO NUEVO salvo H0.2 y H0.4

**H0.1 — Encendido piloto de las features Fase 1-3 existentes.**
- Objetivo: dejar de pagar por features apagadas. Encendido por proyecto piloto.
- Archivo: `.env` del backend en el entorno del operador (`backend/.env` en dev; el `.env` del deploy en `DeployStackyAgents` en producción — NO tocar la DB del deploy).
- Contenido (reemplazar `<PROYECTO>` por el nombre EXACTO del proyecto Stacky activo — verificarlo con `GET /api/projects` o en la UI):
  ```ini
  CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED=true
  CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED=true
  CLAUDE_CODE_CLI_HOOKS_ENABLED=true
  CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED=true
  CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS=<PROYECTO>
  CLAUDE_CODE_CLI_MCP_ENABLED=true
  CLAUDE_CODE_CLI_MCP_PROJECTS=<PROYECTO>
  CLAUDE_CODE_CLI_RESUME_ENABLED=true
  CLAUDE_CODE_CLI_RESUME_PROJECTS=<PROYECTO>
  STACKY_CONTEXT_BUDGET_ENABLED=true
  STACKY_CONTEXT_BUDGET_PROJECTS=<PROYECTO>
  ```
  Memoria colaborativa (`STACKY_MEMORY_INJECTION_ENABLED` + `STACKY_MEMORY_INJECTION_PROJECTS`) recién cuando haya observaciones curadas; es doble gate.
- Aceptación: lanzar un run claude_code_cli sobre un ticket del proyecto piloto; en el log del run deben aparecer "Stacky MCP server inyectado (--mcp-config, F2.1)" y la metadata del execution debe contener `session_id` y `claude_telemetry`. Luego `Invoke-RestMethod "http://localhost:5050/api/metrics/harness-health?days=14"` muestra el run.
- Trampa: allowlist vacía + master ON = TODOS los proyectos (escape hatch); para piloto siempre poblar la allowlist.
- Nota: con H0.4 implementado, este encendido se hace desde el panel de la UI en vez de editar el `.env` a mano (mismo efecto, sin reinicio del backend). El `.env` sigue siendo la fuente persistida.

**H0.2 — `harness_health` multi-runtime.**
- Objetivo: que el dashboard agregue los 3 runtimes, agrupado por runtime.
- Archivos: `backend/services/harness_health.py` (hoy filtra solo `runtime=claude_code_cli`, ver `compute_health :74`), `backend/api/metrics.py:221`.
- Contrato: `compute_health(window_days: int = 14, runtimes: list[str] | None = None)`; respuesta mantiene shape actual y agrega `by_runtime: {<runtime>: {runs, completed_rate, autocorrection_rate, cost_per_ticket, avg_contract_score}}`. Default `runtimes=None` = los 3 (retro-compat: los campos top-level pasan a ser el agregado global; si algún consumidor del frontend asume solo-claude, mantener campo `legacy_claude_only` con el cálculo viejo — verificar consumidores con grep `harness-health` en `frontend/src`).
- TDD: extender `backend/tests/test_harness_health.py` — caso con 1 run codex + 1 run claude: ambos aparecen en `by_runtime`.
- Aceptación: `python -m pytest tests/test_harness_health.py -q` verde.

**H0.3 — Mitigar hazard `_resolve_cwd`.**
- Objetivo: nunca operar en silencio sobre el dir de instalación con skip-permissions ON.
- Archivo: `backend/services/claude_code_cli_runner.py:1504` (`_resolve_cwd`).
- Cambio mínimo: si `workspace_root` viene seteado pero NO existe → levantar `ValueError` (error real, sin fallback); si viene vacío/None → mantener fallback actual pero loguear `warn` y marcar `metadata["cwd_fallback"]=true`.
- TDD: nuevo `backend/tests/test_claude_cli_resolve_cwd.py` — 3 casos (válido / inválido → raises / vacío → fallback con flag).
- Aceptación: pytest del archivo verde + `python -m pytest tests/test_claude_code_cli_phase1.py -q` sin regresión.

**H0.4 — Flags del arnés configurables por UI (~1-2 días, backend + panel frontend).**
- Objetivo: que el operador encienda/apague cada feature del arnés y edite las allowlists por proyecto desde la UI, **sin editar `.env` a mano y sin reiniciar el backend**. H0.1 pasa a ejecutarse desde la UI; todo flag futuro del plan aparece en el panel con solo registrarse.

- **Por qué hoy no alcanza con escribir el `.env` (leer ANTES de implementar)**: los flags son atributos de la instancia singleton `config = Config()` (`backend/config.py:276`) evaluados con `os.getenv(...)` en **import time** (`config.py:151-224`). El endpoint existente `PUT /api/global-config` ya persiste al `.env` y actualiza `os.environ` en caliente (`api/global_config.py:103-135 _write_env`), pero eso NO refresca `config.X`: los runners leen `config.CLAUDE_CODE_CLI_HOOKS_ENABLED` etc. (`claude_code_cli_runner.py:444,:607,:1096`; wrappers en `cli_feature_flags.py:47-110`) y verían el valor viejo hasta reiniciar. El hot-apply correcto y de riesgo mínimo es `setattr(config, KEY, valor_tipado)` sobre la instancia — exactamente el mecanismo ya probado por los tests (`tests/test_claude_code_cli_phase1.py:111-137` lo hacen con monkeypatch). Excepción: `STACKY_MEMORY_INJECTION_ENABLED` NO es atributo de `Config`; se lee de `os.environ` en call time (`cli_feature_flags.py:87`), así que para esa alcanza con el update de `os.environ` que `_write_env` ya hace.

- **Archivos**:
  1. `backend/services/harness_flags.py` (nuevo) — registry declarativo + validación, PURO (no toca disco ni Flask):
     ```python
     from dataclasses import dataclass

     @dataclass(frozen=True)
     class FlagSpec:
         key: str                 # nombre EXACTO de la env var / atributo de Config
         type: str                # "bool" | "csv" | "int"
         label: str               # texto corto para la UI (español)
         description: str         # 1-2 líneas para tooltip (qué hace, fase de origen)
         group: str               # "claude_code_cli" | "global"  (+ "codex_cli" desde H2)
         pair: str | None = None  # key del *_PROJECTS asociado (la UI los renderiza juntos)
         env_only: bool = False   # True = no existe como atributo de Config (solo os.environ)

     FLAG_REGISTRY: tuple[FlagSpec, ...] = (...)  # los 15 actuales, tabla abajo

     def read_current() -> list[dict]:
         # spec + value actual: getattr(config, key) salvo env_only → os.getenv(key)

     def apply_updates(updates: dict[str, object]) -> dict[str, object]:
         # key fuera del registry → ValueError; cast por tipo:
         #   bool: True/False o "true"/"false"/"1"/"yes" (otro string → ValueError)
         #   csv:  normalizar "a , B ," → "a,B"   ·   int: int(str) o ValueError
         # Devuelve {key: valor_tipado}. NO persiste ni aplica (eso es del endpoint).
     ```
     Registro inicial — los 15 flags existentes (todos verificados en `config.py:151-224` y `cli_feature_flags.py`):

     | key | type | group | pair / nota |
     |---|---|---|---|
     | `CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED` | bool | claude_code_cli | F1.1 |
     | `CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED` | bool | claude_code_cli | F1.3 |
     | `CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES` | int | claude_code_cli | — |
     | `CLAUDE_CODE_CLI_HOOKS_ENABLED` | bool | claude_code_cli | F1.4 |
     | `CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED` | bool | claude_code_cli | pair=`..._PROJECTS` |
     | `CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS` | csv | claude_code_cli | — |
     | `CLAUDE_CODE_CLI_RESUME_ENABLED` | bool | claude_code_cli | pair=`..._PROJECTS` |
     | `CLAUDE_CODE_CLI_RESUME_PROJECTS` | csv | claude_code_cli | — |
     | `CLAUDE_CODE_CLI_MCP_ENABLED` | bool | claude_code_cli | pair=`..._PROJECTS` |
     | `CLAUDE_CODE_CLI_MCP_PROJECTS` | csv | claude_code_cli | — |
     | `STACKY_CONTEXT_BUDGET_ENABLED` | bool | global | pair=`..._PROJECTS` |
     | `STACKY_CONTEXT_BUDGET_PROJECTS` | csv | global | — |
     | `STACKY_CONTEXT_BUDGET_TOKENS` | int | global | — |
     | `STACKY_MEMORY_INJECTION_ENABLED` | bool | global | **env_only=True**, pair=`..._PROJECTS` |
     | `STACKY_MEMORY_INJECTION_PROJECTS` | csv | global | — |

  2. `backend/api/harness_flags.py` (nuevo blueprint; registrarlo en `backend/api/__init__.py` con el patrón existente — import del `bp` + `api_bp.register_blueprint(...)`, ver `:13,:40-57`):
     - `GET /api/harness-flags` → `{ok: true, flags: [{key, type, label, description, group, pair, value}]}` (de `read_current()`).
     - `PUT /api/harness-flags` body `{updates: {KEY: value, ...}}` →
       1. `apply_updates()` (ValueError → HTTP 400 con la key ofensora, sin escribir NADA);
       2. persistir con `_write_env` importada de `api.global_config` (`:103` — ya escribe `backend/.env` sin tocar otras claves y actualiza `os.environ`); serializar bool como `"true"`/`"false"` minúscula, int como `str(n)`;
       3. hot-apply: `setattr(config, key, valor_tipado)` para cada key con `env_only=False`;
       4. `logger.info("harness-flags actualizado: %s", keys)` → respuesta `{ok, applied}`.
     - La lista de proyectos para el selector de allowlists NO va acá: el frontend ya consume el endpoint de proyectos existente (`api/projects.py`); componer en el cliente.
  3. `frontend/src/api/endpoints.ts` — nuevo grupo (patrón `ClaudeCli :1455-1477`):
     ```ts
     export interface HarnessFlag {
       key: string; type: "bool" | "csv" | "int"; label: string;
       description: string; group: string; pair?: string | null; value: boolean | string | number;
     }
     export const HarnessFlags = {
       get: () => api.get<{ ok: boolean; flags: HarnessFlag[] }>("/api/harness-flags"),
       save: (updates: Record<string, boolean | string | number>) =>
         api.put<{ ok: boolean; applied: Record<string, unknown> }>("/api/harness-flags", { updates }),
     };
     ```
  4. `frontend/src/components/HarnessFlagsPanel.tsx` (nuevo) — patrón de carga/guardado/estados de `ClaudeCliConfigModal.tsx` (useEffect inicial, loading, resultado). Render: agrupado por `group`; cada bool con `pair` se muestra como fila compuesta "toggle + selector múltiple de proyectos" (opciones del endpoint de proyectos, con entrada de texto libre como fallback); `csv` editable también como texto; `int` como input numérico. **Banner de advertencia OBLIGATORIO** cuando un master queda ON con allowlist vacía: "⚠ se aplica a TODOS los proyectos" (es el escape hatch documentado en `cli_feature_flags.py:8-12` y la trampa #1 de H0.1).
  5. Punto de montaje: junto a la configuración CLI existente — `ClaudeCliConfigModal` se abre desde `AgentLaunchModal.tsx:417`; agregar el acceso al panel en esa misma zona de configuración (confirmar el contenedor real con `grep -rn "ClaudeCliConfigModal" frontend/src` antes de elegir).

- **TDD** (backend primero): `backend/tests/test_harness_flags.py`
  1. Integridad del registry: para cada `FlagSpec` con `env_only=False`, `hasattr(config, key)` es True (un typo en el registry rompe el test, no producción).
  2. `apply_updates`: bool `"true"`→`True`, `"maybe"`→ValueError; key desconocida→ValueError; csv `" A , b ,"`→`"A,b"`; int `"3"`→`3`, `"x"`→ValueError.
  3. API (Flask test client, patrón de los tests de api existentes; `monkeypatch.setattr` de `_ENV_PATH` en `api.global_config` a un `tmp_path`): PUT `{"CLAUDE_CODE_CLI_MCP_ENABLED": true}` → 200; `config.CLAUDE_CODE_CLI_MCP_ENABLED is True` (hot-apply); el `.env` temporal contiene `CLAUDE_CODE_CLI_MCP_ENABLED=true`; `os.environ` actualizado. PUT con key desconocida → 400 y el `.env` temporal NO cambió.
  4. Round-trip: GET refleja el valor tras el PUT.
  5. env_only: PUT `{"STACKY_MEMORY_INJECTION_ENABLED": true}` → `os.environ["STACKY_MEMORY_INJECTION_ENABLED"] == "true"` y `memory_injection_enabled(...)` lo ve sin reinicio.

- **Aceptación**: `python -m pytest tests/test_harness_flags.py -q` verde + `tests/test_claude_code_cli_phase1.py` sin regresión. Manual end-to-end: con backend y frontend corriendo, togglear `CLAUDE_CODE_CLI_MCP_ENABLED` + proyecto piloto desde el panel y lanzar un run claude **sin reiniciar el backend**: el log del run debe mostrar "Stacky MCP server inyectado (--mcp-config, F2.1)".

- **Trampas**:
  - El hot-apply vía `setattr`/`os.environ` es **por proceso**: válido con el backend single-process actual; si algún despliegue usara múltiples workers, solo el proceso que atendió el PUT se entera (el `.env` cubre al resto en el próximo arranque). Verificar cómo se sirve el backend antes de asumir.
  - NO agregar estas keys a `_MANAGED_KEYS` de `global_config.py:34` (ese endpoint es de trackers/binarios/credenciales): el panel nuevo es el **dueño único** de los flags del arnés; dos endpoints escribiendo la misma key del `.env` es la misma divergencia silenciosa que este plan elimina en H3.1.
  - Serialización a `.env`: bools SIEMPRE `"true"`/`"false"` minúscula (los parsers aceptan `("1","true","yes")`); ojo que `_write_env` borra de `os.environ` los valores vacíos — para un CSV vaciado es el comportamiento correcto (`os.getenv` vuelve al default `""`).
  - Sin secrets en el registry (hoy no hay; mantenerlo así — si un flag futuro necesitara un secret, va por `global_config`, no acá).
  - Los tests existentes que monkeypatchean `config.X` siguen válidos: este ítem NO cambia ningún sitio de lectura de flags.
  - En deploy escribe el `.env` del backend que esté corriendo (el de `DeployStackyAgents`); jamás toca la DB. Coherente con H0.1.

- **Regla vinculante para las fases siguientes**: todo flag nuevo que introduce este plan (`CODEX_CLI_CONTRACT_GATE_ENABLED` H2.1, `CODEX_CLI_AUTOCORRECT_*` H2.3, `CODEX_CLI_MCP_*` H2.5, `STACKY_CLI_EGRESS_ENABLED` H3.3, `STACKY_SKILLS_*` H4.3, `STACKY_RUNAWAY_*` H5, `CODEX_CLI_RESUME_*` H7.1) **DEBE agregarse a `FLAG_REGISTRY` en el mismo PR que lo crea** — así aparece en la UI sin tocar el frontend. El test de integridad del registry (TDD #1) verifica la mitad backend automáticamente.

### H1 — Extracción del Harness Core (estructural pero mecánica, ~3-5 días)

**H1.1 — `harness/post_run.py`: pipeline único de finalización.**
- Objetivo: una sola implementación de contrato+confidence+gate, consumida por claude HOY y por codex/copilot en H2/H3.
- Origen del código: el bloque post-run del runner claude que importa `contract_validator` y `confidence` (`claude_code_cli_runner.py:1075-1076` — ubicar la función contenedora con `grep -n "contract_validator" services/claude_code_cli_runner.py`). Mover la lógica a `finalize_run()` (firma en §4) sin cambiar comportamiento; el runner llama a la nueva función.
- Reusar también `artifact_validator.validate_run_artifacts` (`services/artifact_validator.py:257`) dentro de `finalize_run` cuando `CAPABILITIES[runtime].writes_artifacts` y haya `ado_id`.
- TDD (escribir ANTES de mover): `backend/tests/test_harness_post_run.py`:
  1. output válido de functional → `status_suggestion="completed"`, contract score presente;
  2. output que viola contrato duro + `gate_enabled=True` → `"needs_review"`;
  3. ídem con `gate_enabled=False` → `"completed"` (la validación corre igual, solo no gobierna el status — paridad con F1.1);
  4. runtime sin `writes_artifacts` → `artifacts is None`.
  Fixtures de output: copiarlas de `tests/test_claude_code_cli_phase1.py` (no inventar formato).
- Aceptación: `python -m pytest tests/test_harness_post_run.py tests/test_claude_code_cli_phase1.py -q` verde.
- Trampa: NO cambiar las claves de metadata que ya persiste el runner (`contract_result`, `claude_telemetry`, `session_id`) — la UI y `harness_health` las leen.

**H1.2 — `harness/capabilities.py` + registry.**
- Objetivo: capacidad declarada en un solo lugar; los runners y la UI consultan, no adivinan.
- Valores iniciales (verificados contra código): copilot `{agentic:False, writes_artifacts:False, feedback:None, hooks:False, mcp:False, resume:False, model_flag:True, cost:False}`; codex `{agentic:True, writes_artifacts:True, feedback:"resume", hooks:False, mcp:False→True tras H2.5, resume:True, model_flag:True, cost:False→según H2.2}`; claude `{agentic:True, writes_artifacts:True, feedback:"stdin", hooks:True, mcp:True, resume:True, model_flag:True, cost:True}`.
- TDD: `tests/test_harness_capabilities.py` — los 3 runtimes registrados; acceso a runtime desconocido lanza KeyError (sin default silencioso, coherente con la regla de no-fallback).
- Aceptación: pytest verde.

**H1.3 — `harness/telemetry.py`: contrato único.**
- Objetivo: una sola forma de persistir telemetría; los parsers por proveedor son adaptadores.
- Mover la persistencia F1.2 del runner claude (claves bajo `metadata` — `claude_code_cli_runner.py:714-724`) detrás de `telemetry.persist()`, manteniendo las claves EXISTENTES para claude (retro-compat con `harness_health`, que lee `metadata.claude_telemetry.total_cost_usd`) y agregando espejo normalizado `metadata["harness_telemetry"]`.
- TDD: `tests/test_harness_telemetry.py` — persistencia escribe ambas claves; campos faltantes quedan None (nunca KeyError).
- Aceptación: pytest del archivo + `tests/test_harness_health.py` verdes.

### H2 — Paridad codex_cli (≤1 semana, depende de H1)

**H2.1 — Post-run pipeline en codex.**
- Archivos: `services/codex_cli_runner.py` (rama de terminación exitosa — ubicar `_mark_terminal`/status completed entre `:440-560`), `config.py` (agregar tras `CODEX_CLI_APPROVAL :128`):
  ```python
  CODEX_CLI_CONTRACT_GATE_ENABLED   # default "false"
  ```
- Cambio: antes de marcar completed, llamar `harness.post_run.finalize_run(runtime="codex_cli", ...)` con el output final (el runner ya escribe `--output-last-message` a archivo, `:605-637` — usar ese contenido); aplicar `metadata_patch` y el status sugerido solo si el gate está ON.
- TDD: `tests/test_codex_post_run.py` — espejo de los casos de H1.1 con el wiring de codex mockeando el spawn (patrón de mocks: ver `tests/test_claude_code_cli_phase1.py`).
- Aceptación: pytest verde; un run codex real persiste `contract_result` en metadata.
- Trampa: codex materializa TODOS los `.agent.md` en el run_dir (`_materialize_agent_prompts :797`) — el output del agente sigue siendo el last-message file, no confundir.

**H2.2 — Telemetría codex.**
- Objetivo: capturar tokens/turnos si la versión instalada de codex los emite en el JSONL.
- Paso de verificación OBLIGATORIO antes de codear: correr un run codex real y guardar el JSONL crudo (`run_dir`); inspeccionar nombres de eventos (buscar `token`, `usage`, `turn`). NO asumir schema.
- Cambio: en el reader de stdout (cerca de `_extract_codex_session_id :926`), parsear el evento de uso si existe → `RunTelemetry`; si el schema es desconocido, guardar el evento crudo en `RunTelemetry.raw`.
- TDD: `tests/test_codex_telemetry.py` con líneas JSONL fixture tomadas del run real.
- Aceptación: pytest verde; metadata de un run codex contiene `harness_telemetry`.

**H2.3 — Autocorrección codex vía `exec resume` (adaptador del feedback).**
- Objetivo: cerrar en codex la causa raíz #1 ("crea archivos pero no la task") igual que F1.3 en claude.
- Diferencia clave con claude: codex cierra stdin tras el prompt inicial (`codex_cli_runner.py:162-164`); el canal de feedback es `codex exec resume <session_id> "<mensaje>"`, maquinaria que YA existe (`_build_resume_command :639`).
- Cambio: tras el exit del proceso codex y ANTES de finalize: si `CODEX_CLI_AUTOCORRECT_ENABLED` y `artifact_validator.validate_run_artifacts` reporta inválidos → construir mensaje con `cli_autocorrect.build_correction_message(invalid)` (`services/cli_autocorrect.py:39` — reusable, solo depende de `ArtifactValidation`) → lanzar resume con ese mensaje → revalidar. Máx `CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES`-equivalente propio: `CODEX_CLI_AUTOCORRECT_MAX_RETRIES` default 2. Registrar cada intento en el log stream (transparencia al operador).
- Config: `CODEX_CLI_AUTOCORRECT_ENABLED` (default false), `CODEX_CLI_AUTOCORRECT_MAX_RETRIES` (default 2).
- TDD: `tests/test_codex_autocorrect.py` — (1) artifacts válidos → 0 resumes; (2) inválido→válido → 1 resume y completed; (3) siempre inválido → corta en el cap y status needs_review (si gate ON).
- Aceptación: pytest verde.
- Trampa: si no hay `codex_session_id` capturado, NO intentar resume (log warn y seguir al post-run normal).

**H2.4 — Política de modelo para codex.**
- Objetivo: decisión de modelo registrada y con cap configurable, sin inventar un catálogo que no controlamos.
- Archivo: `harness/model_policy.py`:
  ```python
  def resolve_model(runtime: str, requested: str | None) -> tuple[str | None, str]:
      # returns (model, reason). anthropic → llm_router.clamp_model (cap vinculante).
      # codex → passthrough de requested/config.CODEX_CLI_MODEL; si CODEX_CLI_MODEL_DENYLIST
      #   (CSV, default vacío) matchea, degradar a config.CODEX_CLI_MODEL y registrar reason.
  ```
- Cablear en `codex_cli_runner._build_command` (`:605`) reemplazando `model_override or config.CODEX_CLI_MODEL` por `resolve_model(...)`, y persistir `metadata["model_decision"]={model, reason}`.
- TDD: `tests/test_model_policy.py` — anthropic clampa opus→sonnet (reusa `test_llm_router_cap.py` como referencia, NO duplicar sus asserts); codex passthrough; denylist degrada.
- Aceptación: pytest verde. NO tocar el subsistema PM (`api/pm.py`, `cost_estimator`, `pm_llm_client`): tiene catálogo propio fuera de scope.

**H2.5 — MCP para codex (condicional a soporte del binario).**
- Paso de verificación OBLIGATORIO: `codex --help` y `codex exec --help` en la máquina del operador; buscar soporte de MCP por config (`mcp_servers` en `config.toml` / overrides `-c`). Si la versión instalada NO lo soporta → documentar en este archivo y saltear (el file-drop + output_watcher siguen siendo el camino).
- **RESULTADO DE VERIFICACIÓN (2026-06-10)**: el binario `codex` **NO está instalado** en el entorno de desarrollo (`command not found` en bash y PowerShell). H2.5 se pospone hasta que el operador instale y configure el binario codex. El fallback file-drop + output_watcher sigue siendo el canal activo. Ver `harness/capabilities.py`: `CAPABILITIES["codex_cli"].supports_mcp = False`.
- Si en el futuro se instala el binario: verificar con `codex --help` si expone flags MCP, luego implementar espejo de `services/stacky_mcp.py:22 maybe_write_mcp_config`. Flag `CODEX_CLI_MCP_ENABLED` + `CODEX_CLI_MCP_PROJECTS` con helper en `cli_feature_flags.py`. Actualizar `CAPABILITIES["codex_cli"].supports_mcp = True`.
- TDD pendiente: `tests/test_codex_mcp_config.py` — flag OFF → no escribe config; ON+proyecto → escribe y el comando la referencia.
- Aceptación: pytest verde; run real con MCP ON muestra las tools `stacky_*` disponibles.

### H3 — Contrato de salida v1: dueño único + structured-first (≤1 semana, paralelo a H2)

**H3.1 — `harness/run_contract.py`: texto canónico de reglas.**
- Objetivo: eliminar la duplicación `_STACKY_RULES` (`claude_code_cli_runner.py:1112`) vs `_build_codex_prompt` (`codex_cli_runner.py:732`).
- Contrato: `def rules_text(*, runtime: str, mcp_enabled: bool) -> str` — un solo texto fuente; con `mcp_enabled=True` la regla principal es "entregá con `stacky_submit_comment`/`stacky_submit_task`; el file-drop es fallback"; con False, las reglas file-drop actuales (rutas `Agentes/outputs/<ADO_ID>/comment.html`, `epic-<ID>/*/pending-task.json`, **ADO id real, jamás ordinal**).
- Ambos runners consumen `rules_text()`; borrar los textos locales.
- TDD: `tests/test_run_contract.py` — (1) el texto contiene las rutas y la regla de id real; (2) variante MCP menciona las tools; (3) ambos builders de prompt (claude `_build_system_prompt :1238`, codex `_build_codex_prompt :732`) incluyen el texto canónico (asserts de substring sobre los prompts generados con mocks mínimos).
- Aceptación: pytest del archivo + `tests/test_claude_code_cli_prompt.py` verdes.

**H3.2 — Spec del Output Contract v1 + test de consistencia docs-código.**
- Archivo nuevo: `Stacky Agents/docs/specs/output-contract-v1.md` — documenta: schema JSON de `pending-task.json` (campos desde `artifact_validator._required_fields :44`, estados permitidos `:52`), requisitos de `comment.html` (`:220`), layout de carpetas, y la precedencia de canales (MCP submit_* → file-drop validado → output_watcher fallback).
- TDD: `tests/test_output_contract_spec.py` — parsea el .md y verifica que los campos listados == `artifact_validator._required_fields()` (el doc no puede divergir del validador).
- Aceptación: pytest verde.

**H3.3 — Egress check para runtimes CLI (cerrar el hueco de teatro).**
- Hoy `egress_policies.check` solo corre en copilot (`agent_runner.py:651`). Correrlo también sobre el prompt final de claude/codex ANTES del spawn; si bloquea → status error con razón (paridad con copilot).
- Archivos: `claude_code_cli_runner.py` (antes de `_build_command`), `codex_cli_runner.py` (antes de `_write_prompt_to_stdin :396`).
- TDD: `tests/test_cli_egress.py` — prompt con clase bloqueada → run no spawnea.
- Aceptación: pytest verde.
- Riesgo: falsos positivos de egress matan runs → revisar políticas activas antes de prender; gate con flag `STACKY_CLI_EGRESS_ENABLED` default false.

### H4 — Stacky Skills: conocimiento procedimental agnóstico (~1 semana, depende de H1; H2.5 mejora la entrega)

**H4.1 — Formato y storage.**
- Carpeta: `backend/Stacky/skills/*.skill.md` (junto a `Stacky/agents`, mismo modelo mental: fuente canónica local del operador, NO versionada — coherente con `.gitignore:43`). Los defaults de producto pueden viajar como seeds en `backend/packs/` si hiciera falta, NO en `Stacky/skills`.
- Formato (frontmatter YAML, parser: reusar el patrón de `services/vscode_agents.py`):
  ```markdown
  ---
  name: plan-de-pruebas-cliente-x
  description: Cómo estructurar el plan de pruebas para el cliente X (1 línea)
  agents: [qa]            # tipos de agente; vacío = todos
  projects: []            # proyectos Stacky; vacío = todos
  keywords: [plan de pruebas, casos, regresión]
  ---
  (cuerpo: el procedimiento, máx ~1500 tokens)
  ```

**H4.2 — Service.**
- Archivo: `backend/services/stacky_skills.py`:
  ```python
  @dataclass(frozen=True)
  class Skill:
      name: str; description: str; agents: tuple[str, ...]
      projects: tuple[str, ...]; keywords: tuple[str, ...]; body: str; path: str

  def load_skills(root: Path | None = None) -> list[Skill]          # tolera frontmatter roto (skip+log)
  def select_for_run(*, agent_type: str, project: str | None,
                     context_text: str, max_skills: int = 3) -> list[Skill]  # filtro agents/projects + match keywords contra context_text
  def render_index(skills: list[Skill]) -> str                       # "- <name>: <description>" (~50 tokens/skill)
  def get_skill(name: str) -> Skill | None
  ```
- TDD primero: `tests/test_stacky_skills.py` — load con frontmatter válido/roto; select filtra por agente/proyecto/keywords; índice compacto.

**H4.3 — Entrega por runtime (adaptadores, flag `STACKY_SKILLS_ENABLED` + `STACKY_SKILLS_PROJECTS`, OFF).**
- **claude / codex (agénticos)**: inyectar SOLO `render_index()` como sección nueva del system prompt (claude: junto a la sección de `cli_project_knowledge` en `_build_system_prompt :1238`; codex: en `_build_codex_prompt :732`) + instrucción "pedí el cuerpo con la tool `stacky_get_skill`". Nueva MCP tool `stacky_get_skill(name)` en `services/stacky_mcp_tools.py` + dispatch en `stacky_mcp_server.py:153-176` + entrada en tools/list. Si el runtime no tiene MCP activo → inyectar el cuerpo del top-1 skill (cap 1500 tokens) en vez del índice.
- **copilot (one-shot, no puede pedir on-demand)**: inyectar cuerpo del top-1 skill en `compose_system_prompt` (`agents/base.py:56`) como sección nueva con cap, detrás del mismo flag.
- TDD: `tests/test_skills_injection.py` — flag OFF → ni índice ni tool; ON+MCP → índice + tool registrada; ON sin MCP → cuerpo top-1 con cap.
- Aceptación: pytest de ambos archivos + `tests/test_stacky_mcp.py` verdes.

**H4.4 — Tabla de ownership de conocimiento (anti doble-inyección, OBLIGATORIA antes de prender).**

| Tipo de conocimiento | Dueño ÚNICO | Canal |
|---|---|---|
| Procedimientos estables (cómo se hace X acá) | **Stacky Skills (H4)** | índice en system prompt + retrieval MCP |
| Observaciones de runs (resúmenes de sesión) | memoria colaborativa (`memory_store`, tipo `session_summary`) | user prompt (`context_enrichment :338`) |
| Anti-patrones / decisiones / constraints / glosario | tablas FA-* (`anti_patterns`, `decisions`, `constraints`, `glossary`) | system prompt (copilot: `base.py`; CLI: `cli_project_knowledge`) |
| Datos del cliente (rutas, stack, URLs) | `client_profile` | bloque propio en `context_enrichment :222` |
| Ejemplos de outputs buenos | `few_shot` (FA-12) | system prompt copilot |

Regla: una skill NO repite contenido que ya viva en FA-*/memoria. Al crear una skill que solape, migrar el contenido, no duplicarlo.

### H5 — Runaway guard in-run (≤3 días, depende de H1.3)

- Objetivo: ningún run agéntico puede quemar turnos/costo sin techo (hoy: `CLAUDE_CODE_CLI_TIMEOUT=0` y nada más).
- Archivo: `harness/runaway_guard.py`:
  ```python
  @dataclass(frozen=True)
  class RunLimits:
      max_turns: int      # 0 = sin límite
      max_cost_usd: float # 0.0 = sin límite

  class RunawayGuard:
      def __init__(self, limits: RunLimits): ...
      def observe(self, *, num_turns: int | None = None,
                  cost_usd: float | None = None) -> str | None:
          """None si OK; razón legible si se excedió (primera vez sola)."""
  ```
- Config: `STACKY_RUNAWAY_MAX_TURNS` (default 0=off), `STACKY_RUNAWAY_MAX_COST_USD` (default 0=off). Defaults generosos sugeridos al activar: 80 turnos / 5.0 USD.
- Cableado claude: en el reader del stream (donde F1.2 acumula telemetría, `claude_code_cli_runner.py:602`), contar eventos de turno del assistant y costo incremental si está disponible; al exceder → 1 mensaje por stdin pidiendo cierre+resumen, gracia de 60s, luego `terminate` → status `needs_review` + `metadata["runaway"]={reason, turns, cost}`. NUNCA descartar el trabajo ya hecho.
- Cableado codex: contar eventos del JSONL (turnos solamente; costo no disponible hasta H2.2); al exceder → terminate → needs_review (codex no tiene stdin abierto: sin mensaje de cierre).
- TDD: `tests/test_runaway_guard.py` — límites 0 = nunca dispara; excede turnos → razón una sola vez; excede costo → razón.
- Aceptación: pytest verde; los tests de fase 1 claude sin regresión.

### H6 — Evals: harvest de goldens + cobertura + gate suave (~1 semana, independiente)

**H6.1 — `python -m evals harvest <execution_id> [--name <caso>]`.**
- Objetivo: convertir runs reales buenos en golden cases sin escribirlos a mano (hoy hay 3 casos, solo functional+qa).
- Archivos: `backend/evals/__main__.py` (subcomando), `backend/evals/harvest.py` nuevo.
- Comportamiento: lee `AgentExecution` (output + agent_type), aplica PII mask (`services/pii_masker.py` — mismo seam que usan los runners), calcula el contract score actual y escribe `evals/agents/<agent_type>/<name>.json` con el formato EXISTENTE del golden_runner: `{name, agent_type, output, expect: {min_score: <floor(score actual)>, must_pass: true}}`. Falla con mensaje claro si el execution no existe o no está completed.
- TDD: `tests/test_evals_harvest.py` — sobre una fila de execution fixture (patrón de DB en tests existentes, p. ej. `tests/test_harness_health.py`).
- Aceptación: `python -m pytest tests/test_evals_harvest.py tests/test_evals_golden.py -q` verde; `python -m evals list` muestra el caso nuevo.

**H6.2 — Cobertura mínima por agente activo.**
- Tarea operativa post-H6.1: cosechar ≥3 goldens por cada `agent_type` con contrato definido en `contract_validator._CONTRACTS :50` (hoy functional y qa tienen 3 en total; developer/technical tienen 0).
- Aceptación: `python -m evals run all` → exit 0 con ≥3 casos por agente cubierto.

**H6.3 — Gate suave al editar un `.agent.md`.**
- Ubicar el endpoint de guardado de agentes: `grep -n "agent" "Stacky Agents/backend/api/agents.py"` (los `.agent.md` se editan vía UI/API o a mano en `backend/Stacky/agents/`; también existe `services/manifest_watcher.py`). Tras un guardado, disparar en thread los evals del `agent_type` afectado y registrar el resultado como warning en el log + respuesta (`{"evals_warning": ...}`). NO bloquear el guardado.
- TDD: `tests/test_agent_save_eval_gate.py` — guardado dispara evals (mockeados) y no bloquea ante fallo.
- Trampa: los goldens NO referencian el contenido del `.agent.md` (gitignored, cambia por cliente); el juez es siempre `contract_validator` sobre el output congelado.

### H7 — Resume unificado + reproducibilidad (~3 días, depende de H1.2)

**H7.1 — `harness/resume.py`.**
- Objetivo: una sola decisión de "¿continúo sesión previa?" para los runtimes con `supports_session_resume`.
- Contrato: `def resolve(*, runtime: str, ticket_id: int, agent_type: str, project: str | None) -> tuple[str | None, str | None]` → `(session_ref, delta_prefix)`. Implementación: extraer la lógica de claude `_resolve_resume` (`claude_code_cli_runner.py:1153`, ya integra `delta_prompt.py` + flags por proyecto) y parametrizar la clave de metadata de sesión (`session_id` claude / `codex_session_id` codex, capturada en `codex_cli_runner.py:954-965`).
- Cablear re-run codex: flag `CODEX_CLI_RESUME_ENABLED` + `_PROJECTS` (helper en `cli_feature_flags`); si hay sesión previa para ticket+agente → `codex exec resume <id>` con delta prompt en lugar de arranque en frío.
- TDD: `tests/test_harness_resume.py` — sin sesión previa → (None, None); con sesión + flag ON → ref correcta por runtime; flag OFF → (None, None).
- Aceptación: pytest verde + `tests/test_cli_resume_mcp_config.py` sin regresión.

**H7.2 — `repro.ps1` para codex.**
- El runner claude ya genera script de reproducción (F1.2). Espejarlo en codex: escribir `run_dir/repro.ps1` con comando exacto + env `STACKY_*` no sensibles (filtrar con `services/agent_env.py:118 is_denied`).
- TDD: assert en `tests/test_codex_post_run.py` de que el archivo existe tras un run mockeado.

### H8 — Observabilidad del valor agregado (continuo, cierra el loop)

- KPI explícitos en `harness_health` (sobre lo de H0.2): por runtime y proyecto — % runs completed sin intervención, # autocorrecciones que salvaron un run (claude: `metadata` del AutocorrectLoop `summary() :109`; codex: H2.3), costo por ticket, contract score promedio, hit-rate de memoria (ya persistido en block metadata, `context_enrichment.py`), runs frenados por runaway.
- Estos números SON el argumento "Stacky vs CLI pelado": cada autocorrección exitosa es un run que el CLI pelado habría entregado roto.
- UI opcional: tarjeta en el dashboard que consuma `GET /api/metrics/harness-health` (componente nuevo en `frontend/src/components/`, patrón de los existentes).

---

## 6. Priorización (impacto vs esfuerzo/riesgo)

**Quick-wins (≤1 día c/u):**
| Ítem | Impacto | Por qué primero |
|---|---|---|
| H0.1 activar flags piloto | ALTÍSIMO | valor ya construido y pagado; solo .env |
| H0.2 health multi-runtime | Alto | sin medición no se puede demostrar valor |
| H0.3 fix `_resolve_cwd` | Medio | hazard real con skip-permissions ON |
| H0.4 flags configurables por UI (~1-2 días) | Alto | el encendido piloto deja de requerir `.env` + reinicio; todo flag futuro aparece en la UI con solo registrarse |
| H3.1 dueño único de reglas | Alto | elimina divergencia silenciosa; mecánico |

**Medianas (≤1 semana c/u):**
| Ítem | Impacto |
|---|---|
| H1 Harness Core (extracción) | Alto (habilita todo lo demás; riesgo bajo: mover código probado) |
| H2.1-H2.3 paridad codex (post-run + autocorrección) | ALTÍSIMO (el 2º runtime agéntico hoy corre a ciegas) |
| H6 evals harvest + gate | Alto (editar prompts deja de probarse en producción) |
| H5 runaway guard | Medio-alto (techo de costo) |
| H4 Stacky Skills | Alto (diferencial puro vs CLI pelado) |
| H7 resume unificado + repro codex | Medio |

**Estructurales (varias semanas, por etapas):**
| Ítem | Impacto |
|---|---|
| H3.2-H3.3 Output Contract v1 + MCP-first + egress CLI | ALTÍSIMO a mediano plazo: structured outputs imposibles de romper |
| H2.5 MCP codex (condicional al binario) | Alto si el binario lo soporta |
| H8 KPIs de valor | Alto (es la prueba del valor agregado) |

**Orden recomendado de ejecución**: H0 → H1 → H2.1-H2.3 → H3.1 → H6.1 → H5 → H4 → H7 → H3.2/H3.3 → H2.5 → H8 (H8 se alimenta de todo lo anterior).

---

## 7. Dependencias

```
H0.1 (flags ON) ────────────→ datos reales para H8 y calibración H5
H0.4 (FLAG_REGISTRY + panel UI) ──→ todo flag nuevo de H2/H3.3/H4/H5/H7 se registra ahí (UI sin tocar el frontend)
H1.1-H1.3 (core) ──→ H2.1/H2.2 (codex) ──→ H2.3 (autocorrect codex)
H1.2 (capabilities) ──→ H7.1 (resume unificado)
H1.3 (telemetry) ──→ H5 (runaway) y H8 (KPIs)
H3.1 (rules únicas) ──→ H3.2 (spec) ──→ H3.3 (MCP-first en reglas)
H2.5 (MCP codex) ──→ mejora H4.3 (skills on-demand en codex)
H6.1 (harvest) ──→ H6.2 (cobertura) ──→ H6.3 (gate)
```

---

## 8. Qué NO hacer (anti-scope explícito — esto lo haría PEOR)

1. **RBAC / multiusuario / validación de `current_user`** — no hay sustrato de auth; sería teatro que complica todo. Stacky es mono-operador por diseño hoy.
2. **Wrapper PowerShell de los CLIs** — veredicto técnico cerrado (`PLAN-ROBUSTECIMIENTO-ARNES.md §5.1`): rompe kill/stderr/encoding/escaping. No re-proponer.
3. **Quitar `--dangerously-skip-permissions` o meter allowlists de tools por default** — decisión vinculante (§5.3); F3.4 quedó descartada. La mitigación es validación de artifacts, no permisos.
4. **Modelos por encima de Sonnet en el path Claude** — `clamp_model` es vinculante, incluso contra override del operador.
5. **Subagentes/orquestación multi-agente propia de Stacky** — los CLIs agénticos ya traen subagentes; duplicar la orquestación quema tokens y duplica fallas. El valor de Stacky está en el arnés, no en re-implementar el loop agéntico.
6. **Un 4º canal de inyección de conocimiento** — B5/B6: cada tipo de conocimiento tiene UN dueño (tabla H4.4). Cualquier feature nueva de "contexto" debe encajar en un canal existente o reemplazarlo, jamás sumarse.
7. **Reescribir los runners sobre un framework/SDK** — el Harness Core es extracción de código probado con tests; cualquier "plugin system" genérico es abstracción prematura.
8. **Tocar el subsistema PM** (`api/pm.py`, `services/cost_estimator.py`, `pm_llm_client`) — catálogo de modelos propio, fuera de scope.
9. **Eliminar `output_watcher`/`agent_completion`** — siguen siendo la red de seguridad hasta que H2/H3 demuestren tasa de éxito superior con datos de H8.
10. **Gates bloqueantes en evals o en runaway al inicio** — todo gate nace advirtiendo (`needs_review`/warning), nunca descartando trabajo; se endurece solo con evidencia.

---

## 9. Trampas del entorno (checklist para el implementador)

- [ ] `.agent.md` y todo `backend/Stacky/*` están gitignored (`.gitignore:43`); el runtime lee de `backend/Stacky/agents`, NUNCA de `DeployStackyAgents`.
- [ ] DB viva de producción: `Stacky Agents/DeployStackyAgents/data`. Dev: `backend/data/stacky_agents.db`. Tests: DB temporal propia (ver fixtures existentes).
- [ ] Outputs de agentes caen en la máquina del operador (`C:\desarrollo\...\Agentes\outputs`), no en el repo.
- [ ] Suite completa de tests contaminada: validar SIEMPRE por archivo; baseline con `git stash` si tocás contratos compartidos.
- [ ] PowerShell 5.1: sin `&&`, sin `2>&1` sobre exes nativos; here-strings con `'@` en columna 0.
- [ ] Flags: patrón `*_ENABLED` (master) + `*_PROJECTS` (CSV allowlist); allowlist vacía + master ON = todos los proyectos; dueño único `services/cli_feature_flags.py`.
- [ ] Todo flag nuevo `*_ENABLED`/`*_PROJECTS` se agrega a `FLAG_REGISTRY` (`services/harness_flags.py`, H0.4) en el MISMO PR que lo crea — si no, no existe para la UI. Recordá: los flags de `Config` se leen en import time; el hot-apply es `setattr(config, ...)` + `os.environ`, nunca solo el `.env`.
- [ ] Claves de metadata existentes (`contract_result`, `claude_telemetry`, `session_id`, `codex_session_id`) son contrato con la UI y harness_health: agregar, no renombrar.
- [ ] "Solo Stacky escribe en ADO": todo camino de publicación pasa por `ado_write_outbox` — los MCP `submit_*` validan y ENCOLAN, no publican.
- [ ] Sin fallback silencioso entre runtimes; errores de runner son errores reales.
