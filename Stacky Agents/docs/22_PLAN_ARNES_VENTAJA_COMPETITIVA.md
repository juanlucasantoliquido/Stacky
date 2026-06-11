# 22 — Plan Arnés v3: de "hardening" a ventaja competitiva

**Fecha:** 2026-06-10
**Estado:** propuesto (ningún ítem implementado)
**Predecesores:** `PLAN-ROBUSTECIMIENTO-ARNES.md` (F1-F3, implementado) y `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia, diseño con archivos exactos, criterios de aceptación, tests TDD y complejidad.

---

## 1. Punto de partida (qué YA existe — no re-implementar)

Verificado contra el código el 2026-06-10 en `feat/memoria-colaborativa-hardening`:

| Capacidad | Dónde vive | Estado |
|---|---|---|
| Contract gate + confidence post-run | `harness/post_run.py::finalize_run` (claude + codex) | OK |
| Telemetría normalizada | `harness/telemetry.py` (persiste `harness_telemetry`) | OK (costo solo si el CLI lo reporta) |
| Autocorrección | `services/cli_autocorrect.py` (claude), `services/codex_autocorrect.py` (codex) | OK |
| Reglas de contrato compartidas | `harness/run_contract.py` (`_STACKY_RULES` es alias de compat, claude_code_cli_runner.py:1289) | OK |
| Capacidades por runtime | `harness/capabilities.py` (`supports_mcp`, `supports_resume`, `supports_stdin_feedback`) | OK |
| Política de modelo + cap duro sonnet | `harness/model_policy.py`, `services/llm_router.py::clamp_model` | OK |
| Skills | `services/stacky_skills.py` + inyección en 3 runtimes + MCP tool `stacky_get_skill` | OK |
| Runaway guard (turnos/costo) | `harness/runaway_guard.py`, cableado en ambos runners CLI | OK |
| Evals golden + harvest + gate suave en import | `backend/evals/` (`golden_runner`, `harvest`, `eval_gate`) | OK |
| Resume multi-runtime + repro.ps1 | `harness/resume.py`, `write_repro_script` en ambos runners | OK |
| Reaper de runs colgados | `services/ticket_status.py::recover_stale_running_tickets` + daemon en `app.py:257-273` + `services/heartbeat_monitor.py` | OK |
| Outbox ADO idempotente | `services/ado_write_outbox.py` (idempotency_key, backoff exponencial, `dead_letter`, MAX_ATTEMPTS=6) | OK |
| KPIs del arnés | `services/harness_health.py` + `GET /api/metrics/harness-health` + `HarnessHealthCard.tsx` | OK |
| Memoria colaborativa Fase A | `services/memory_store.py` + `api/memory` + seam en `context_enrichment.py` | OK (flags OFF, B5 parcial) |
| MCP submit_* (validan y encolan, no publican) | `services/stacky_mcp_server.py` / `stacky_mcp_tools.py` | OK (solo claude; codex `supports_mcp=False`) |

**Restricciones vinculantes (no relitigar):**
- Cap duro de modelo: nunca por encima de `claude-sonnet-4-6` (clamp único en `llm_router.clamp_model`).
- `--dangerously-skip-permissions` siempre activo en el CLI.
- Sin wrapper PowerShell alrededor de los CLIs.
- "Solo Stacky escribe en ADO": todo pasa por `ado_write_outbox`.
- Stacky es mono-operador: no construir RBAC/roles (no hay sustrato de auth real); la gobernanza es por guardrails técnicos, no por permisos.
- Claves de metadata existentes (`runtime`, `session_id`, `codex_session_id`, `contract_result`, `claude_telemetry`, `runaway`) son contrato: agregar claves, nunca renombrar.
- Todo flag nuevo `*_ENABLED`/`*_PROJECTS` entra en `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR.
- Suite completa de tests contaminada (~40F/449E en HEAD): validar SIEMPRE por archivo; baseline vía `git stash` si se tocan contratos compartidos.

---

## 2. Diagnóstico: debilidades concretas con evidencia

| # | Debilidad | Evidencia | Impacto |
|---|---|---|---|
| **D1** | **El arnés está construido pero apagado.** 26 flags en `FLAG_REGISTRY`, **cero** con default ON; no hay presets ni perfil de activación. El operador tendría que conocer y togglear ~26 flags uno por uno. | `services/harness_flags.py` (26 `FlagSpec(`, 0 `default=True`) | Todo el valor de F1-F3 + H0-H8 + memoria es invisible en producción. La "ventaja competitiva" hoy es teórica. |
| **D2** | **Selección de runtime 100% manual.** El operador elige runtime en el payload (default `github_copilot`); `/route` solo preselecciona modelo (FA-04). Los KPIs de `harness_health` (éxito, costo, autocorrección por runtime) existen pero nadie los usa para decidir. | `api/agents.py:240-340` (dispatch por payload), `api/agents.py:343-357` (`/route` = solo modelo) | Decisiones subóptimas de costo/calidad; el conocimiento operacional acumulado no retroalimenta nada. |
| **D3** | **Sin guard de duplicados ni límite de concurrencia.** El launch no verifica si ya hay un run activo del mismo ticket+agente; no existe `Semaphore`/`MAX_CONCURRENT` en todo el backend. N clicks = N subprocesos CLI simultáneos. | `api/agents.py:319-336` (llama `run_agent` sin guard); grep `Semaphore|MAX_CONCURRENT` → 0 matches | Trabajo duplicado, costo duplicado, riesgo de outputs pisándose en el mismo cwd, máquina del operador saturada. |
| **D4** | **Costo invisible cuando el CLI no lo reporta.** La telemetría toma `total_cost_usd` del evento del CLI; codex no lo emite → `cost_per_ticket=null`. No hay tabla de precios para estimar desde tokens. | `harness/telemetry.py:85` (`event.get("total_cost_usd") or event.get("cost_usd")`); H8: `runs_with_cost`/null para codex | El KPI económico (argumento central de venta del arnés) queda incompleto para todo runtime no-claude. |
| **D5** | **Prompts de agente sin versionado ni trazabilidad.** Los `.agent.md` están gitignored (`.gitignore:43`); `AgentExecution` no guarda hash/versión del prompt usado (el único `prompt_hash` del repo es el del cache). | `models.py:206-236` (sin columna/metadata de prompt); grep `prompt_hash` → solo `services/output_cache.py` | Imposible correlacionar regresión de calidad con un cambio de prompt, hacer rollback, o auditar "qué prompt corrió este run". Los prompts (activo principal) no tienen historia. |
| **D6** | **El path frágil de outputs file-based sigue vivo para codex.** `supports_mcp=False` → codex no usa los `submit_*` validados server-side; sus outputs van por archivos + output_watcher + parsing. Esa es exactamente la causa raíz del bug histórico "crea archivos pero no la task" (JSON inválido + ordinal vs ADO id). | `harness/capabilities.py:35`; incidente doc `20_INCIDENTE_ADO_241...` | El guardrail más fuerte del arnés (validación antes de encolar) solo protege a claude. Cada runtime nuevo sin MCP hereda el path frágil. |
| **D7** | **Sin CI y suite no confiable.** No existe `.github/workflows/`; la suite completa da ~40F/449E por polución entre tests (sqlite in-memory compartido / singletons), aunque los archivos pasan aislados. Las evals tampoco corren automáticamente (solo gate suave en import). | Glob `.github/workflows/*` → vacío; baseline verificado 2026-06-09 vía stash | Las regresiones del arnés solo se detectan si alguien corre tests por archivo a mano. El arnés protege a los agentes pero nada protege al arnés. |
| **D8** | **Sin taxonomía de fallos.** `error_message` es texto libre; `harness_health` no desglosa por causa (spawn vs timeout vs contrato vs runaway). | `models.py:220`; `services/harness_health.py` (sin breakdown de causa) | No se puede responder "¿en qué falla más el arnés?" sin leer logs. Sin eso, no hay priorización basada en datos. |
| **D9** | **Doble canal de conocimiento aún solapable (B5 parcial).** FA-* (tablas propias → system prompt) y `memory_store` (→ user prompt) coexisten; la separación es por convención (`_CAPTURE_TYPE="session_summary"`), pero `POST /api/memory` acepta tipo libre y `get_context_for_run` no filtra. | `services/memory_store.py`, `services/context_enrichment.py`; plan v2 de memoria (Opción A diferida) | Riesgo de doble inyección del mismo conocimiento (tokens duplicados + contradicciones). |
| **D10** | **Cache/dedup de outputs solo en copilot.** `output_cache` lo usa únicamente `speculative.py`; los runtimes CLI re-ejecutan trabajo idéntico sin detección. | grep `output_cache` → `speculative.py`, `db.py`, tests | Re-runs idénticos pagan costo completo. Menor, pero es dinero recurrente. |

**Lectura estratégica:** las fases anteriores construyeron los músculos del arnés (validación, telemetría, resiliencia). Lo que falta es (a) **encenderlo** de forma gestionable, (b) **cerrar los dos huecos de cobertura** (codex file-based, costo no-claude), (c) **que el arnés se use a sí mismo** (KPIs → decisiones, fallos → taxonomía → priorización, prompts → versiones → evals), y (d) **protegerse a sí mismo** (CI). Eso es lo que convierte features sueltas en plataforma.

---

## 3. Hoja de ruta

Tres fases. Cada ítem indica complejidad (S ≤ ½ día, M ≤ 2 días, L > 2 días para un dev agéntico) y dependencias. Orden de ejecución recomendado: V0 completo → V1.1, V1.3, V1.4a-b → resto de V1 → V2.

### FASE V0 — Quick wins: encender y blindar lo que ya existe (todo S)

---

#### V0.1 Perfiles de arnés (presets de flags)

- **Ataca:** D1.
- **Objetivo:** que activar el arnés sea UNA decisión ("perfil"), no 26. Invisible para el dev: elige `full` y todo lo construido empieza a trabajar.
- **Diseño:**
  - Nuevo `backend/services/harness_profiles.py`:
    ```python
    PROFILES: dict[str, dict[str, str]] = {
        "off":  {},  # explícito: aplicar = apagar todos los flags del universo gestionado
        "safe": {    # solo guardrails sin efectos de inyección de contexto
            "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED": "true",
            "CODEX_CLI_CONTRACT_GATE_ENABLED": "true",
            "STACKY_RUNAWAY_MAX_TURNS": "80",
            "STACKY_RUNAWAY_MAX_COST_USD": "5.0",
            # + telemetría/autocorrect si están flaggeados
        },
        "full": { ...todo safe + skills, memoria (inyección+captura), resume, MCP, knowledge... },
    }
    def apply_profile(name: str) -> dict[str, str]:  # devuelve {flag: valor_aplicado}
    def detect_profile() -> str | None:              # compara valores actuales vs presets
    ```
    `apply_profile` reusa el mecanismo hot-apply existente de `harness_flags` (setattr en `config` + `os.environ`) — NO inventa otro canal de escritura. El universo gestionado = exactamente las claves listadas en los presets (un perfil nunca toca flags fuera de su lista, salvo `off` que apaga la unión de claves de todos los presets).
  - Config nuevo: `STACKY_HARNESS_PROFILE` (str, default `""`). Si está seteado, `app.py` aplica el perfil en el startup (después de cargar config, antes del reaper). Un env explícito individual seteado por el operador GANA sobre el perfil (regla: el perfil solo aplica claves cuya env var no esté definida explícitamente).
  - Endpoint: `POST /api/harness-flags/profile` body `{"name": "full"}` → 200 con el dict aplicado; `GET /api/harness-flags` agrega campo `"active_profile"` (resultado de `detect_profile()`).
  - Frontend: selector de perfil (3 botones) arriba de la lista de flags existente en la página de flags/diagnóstico.
- **Criterios de aceptación:**
  1. `POST profile {"name":"full"}` enciende los flags del preset y `GET` los refleja al instante (sin reiniciar).
  2. Boot con `STACKY_HARNESS_PROFILE=safe` arranca con esos valores; una env var explícita individual no es pisada.
  3. Perfil desconocido → 400 con lista de perfiles válidos.
  4. `detect_profile()` devuelve el nombre si los valores coinciden exactamente, si no `None` (estado "custom").
- **Tests (TDD, `tests/test_harness_profiles.py`):** aplicar cambia config+env; `off` apaga la unión; env explícito gana en boot; perfil desconocido ValueError; detect en los 4 estados (off/safe/full/custom).

---

#### V0.2 Guard anti-duplicados en el launch

- **Ataca:** D3 (mitad dedup).
- **Objetivo:** que lanzar dos veces el mismo agente sobre el mismo ticket sea imposible por accidente.
- **Diseño:**
  - Nuevo `backend/services/run_guard.py`:
    ```python
    ACTIVE_STATUSES = ("preparing", "running")
    def find_active_run(session, ticket_id: int, agent_type: str) -> AgentExecution | None
    ```
  - En `api/agents.py` (endpoint de run, antes de la línea ~319 donde llama `agent_runner.run_agent`): si `find_active_run(...)` y `payload.get("force") is not True` → `409` con `{"ok": false, "error": "duplicate_run", "active_execution_id": N, "hint": "reintentar con force=true"}`.
  - Frontend: ante 409 `duplicate_run`, mostrar confirm "Ya hay un run activo (#N). ¿Lanzar igual?" → reintenta con `force=true`.
- **Criterios de aceptación:** lanzar con run activo mismo ticket+agente → 409; con `force=true` → 202; run en estado terminal (`completed`/`error`/`needs_review`) no bloquea; runs de OTRO agent_type sobre el mismo ticket no bloquean.
- **Tests (`tests/test_run_guard.py`):** los 4 casos de aceptación + `find_active_run` puro con fixtures de DB.

---

#### V0.3 Límite de concurrencia de runs CLI

- **Ataca:** D3 (mitad concurrencia).
- **Objetivo:** techo de subprocesos CLI simultáneos en la máquina del operador.
- **Diseño:**
  - Config: `STACKY_MAX_CONCURRENT_RUNS` (int, default `0` = ilimitado, retro-compat). Registrar en `FLAG_REGISTRY` (tipo int ya soportado; float se agregó en H5).
  - Nuevo `backend/services/run_slots.py`: contador global thread-safe (no `BoundedSemaphore` bloqueante — chequeo no bloqueante):
    ```python
    def try_acquire() -> bool   # False si activos >= límite (límite 0 = siempre True)
    def release() -> None       # idempotente, nunca negativo
    def active_count() -> int
    ```
  - Chequeo EN EL LAUNCH (`api/agents.py`, después del guard V0.2): si `not try_acquire()` → `429` `{"ok": false, "error": "max_concurrent_runs", "active": N, "limit": M}`. Sin cola: mono-operador, feedback inmediato es mejor que encolar en silencio.
  - `release()` en el `finally` del cierre de run de ambos runners CLI (`claude_code_cli_runner._run_in_background`, `codex_cli_runner._run_in_background`) y en el path de error temprano de `agent_runner.run_agent` (si el spawn falla antes de llegar al runner). Para `github_copilot` (sin subproceso) NO aplica el slot (adquirir solo cuando `runtime in ("claude_code_cli","codex_cli")`).
- **Criterios de aceptación:** con límite 2 y 2 runs activos, el tercero recibe 429; al terminar uno, el siguiente entra; límite 0 nunca rechaza; crash del runner libera el slot (vía finally); `active_count` visible en `GET /api/metrics/harness-health` (campo nuevo `active_runs`).
- **Tests (`tests/test_run_slots.py`):** acquire/release puros, límite 0, release idempotente, integración launch→429.

---

#### V0.4 Taxonomía de fallos (`failure_kind`)

- **Ataca:** D8. Prerrequisito de V1.2 y V2.2.
- **Objetivo:** que cada run terminado en error tenga una causa clasificada y agregable.
- **Diseño:**
  - Nuevo `backend/harness/failure.py`:
    ```python
    KINDS = ("spawn_error", "timeout", "runaway", "contract_failed", "cancelled", "crash")
    def classify(*, return_code: int | None, error_message: str | None,
                 metadata: dict) -> str | None   # None si el run fue ok
    ```
    Reglas deterministas (en orden): `metadata.get("runaway")` → `runaway`; cancelación explícita (metadata/flag del runner) → `cancelled`; mensaje de timeout de sesión (cap `CLAUDE_CODE_CLI_TIMEOUT`, claude_code_cli_runner.py:758) → `timeout`; fallo al spawnear (sin PID/`FileNotFoundError`) → `spawn_error`; `contract_result` con `passed=False` y status `needs_review` → `contract_failed`; resto con return_code != 0 → `crash`.
  - Cableado: en `harness/post_run.py::finalize_run` y en los paths de error de ambos runners CLI (donde hoy escriben `output_data={"runtime":..., "error":...}` — claude_code_cli_runner.py:983, codex_cli_runner.py:773) → `metadata["failure_kind"] = classify(...)`. Clave NUEVA, no renombra nada.
  - `services/harness_health.py`: agregar `failure_kinds: dict[str, int]` global y por runtime (mismo patrón que `runaway_stops` de H8, graceful si la clave no existe en runs viejos).
  - `HarnessHealthCard.tsx`: fila "Top fallos" (kind: count, ordenado desc).
- **Criterios de aceptación:** cada combinación de la tabla de reglas produce el kind esperado; runs ok → sin clave; harness-health expone el breakdown; runs históricos sin la clave no rompen el agregado.
- **Tests:** `tests/test_harness_failure.py` (tabla parametrizada de casos), extensión de `tests/test_harness_health.py` (breakdown + graceful).

---

#### V0.5 Normalización de costo multi-proveedor (pricing fallback)

- **Ataca:** D4.
- **Objetivo:** que TODO run tenga costo (reportado o estimado), para que el KPI económico funcione con cualquier runtime/modelo.
- **Diseño:**
  - Nuevo `backend/harness/pricing.py`:
    ```python
    # USD por millón de tokens, match por prefijo de model id (más largo gana)
    DEFAULT_PRICES: dict[str, tuple[float, float]] = {
        "claude-sonnet-4": (3.0, 15.0), "claude-haiku-4": (1.0, 5.0),
        "gpt-5": (...), "o4": (...),  # completar con la tabla vigente al implementar
    }
    def estimate_cost(model: str | None, input_tokens: int | None,
                      output_tokens: int | None) -> float | None
    ```
    Override por env `STACKY_PRICING_JSON` (JSON con el mismo shape) para actualizar precios sin deploy. Sin match de prefijo o sin tokens → `None` (nunca inventar).
  - `harness/telemetry.py`: en `from_codex_event` y `from_stream`, si `total_cost_usd is None` y hay tokens → `total_cost_usd = estimate_cost(...)` y campo nuevo `cost_estimated: bool = True` (en el dataclass y en `to_dict`). Costo reportado por el CLI siempre gana.
  - `services/harness_health.py`: `runs_with_cost` pasa a incluir estimados; campo nuevo `estimated_cost_runs: int` para transparencia.
- **Criterios de aceptación:** evento codex con `token_count` y sin costo → telemetría con costo estimado y `cost_estimated=true`; evento claude con `total_cost_usd` → ese valor, `cost_estimated=false`; modelo desconocido → costo null (no 0.0); `STACKY_PRICING_JSON` malformado → log warn + tabla default (nunca crash).
- **Tests:** `tests/test_harness_pricing.py` (match por prefijo más largo, sin tokens, override env, malformado) + extensión de `tests/test_codex_telemetry.py`.

---

### FASE V1 — Estructurales: cerrar los huecos de cobertura (M)

---

#### V1.1 Versionado y trazabilidad de prompts de agente

- **Ataca:** D5. Prerrequisito de V2.2/V2.3/V2.4.
- **Objetivo:** que cada `.agent.md` tenga historia auditable y cada run sepa exactamente qué versión de prompt corrió. Como los `.agent.md` están gitignored, **la DB es el único lugar posible para ese historial**.
- **Diseño:**
  - Modelo nuevo en `models.py`:
    ```python
    class AgentPromptVersion(Base):
        __tablename__ = "agent_prompt_versions"
        id: int (pk); filename: str(200) index; sha256: str(64) index
        body: Text                # cuerpo completo: gitignored ⇒ sin otra fuente
        imported_at: datetime; source: str(40)  # "import_endpoint" | "fs_scan"
        __table_args__ = (UniqueConstraint("filename", "sha256"),)
    ```
    Tabla nueva ⇒ `Base.metadata.create_all` la crea; sin migración destructiva.
  - Captura en el punto único de escritura: `api/agents.py::stacky_import_agent` (línea ~119, el mismo lugar donde H6 disparó el eval gate) → tras guardar el archivo, `INSERT OR IGNORE` de la versión (helper `services/agent_prompt_registry.py::record_version(filename, body, source)` que calcula sha256 y respeta el unique).
  - Sello en el run: ambos runners CLI ya leen el `.agent.md` para armar el system prompt → calcular `sha256` del cuerpo leído y escribir `metadata["prompt_sha"] = sha` (clave nueva). Si la versión no existe en la tabla (archivo editado a mano por fuera del import), `record_version(..., source="fs_scan")` la registra en ese momento — así el historial nunca tiene huecos.
  - Endpoints: `GET /api/agents/<filename>/versions` (lista: id, sha256, imported_at, source, size) y `GET /api/agents/<filename>/versions/diff?from=<id>&to=<id>` (unified diff con `difflib`, text/plain).
- **Criterios de aceptación:** importar el mismo body dos veces → 1 versión; body distinto → 2; un run CLI siempre persiste `prompt_sha`; editar el archivo a mano y correr → la versión aparece con `source="fs_scan"`; el diff entre dos versiones es correcto; nada de esto toca el flujo si la tabla está vacía (retro-compat).
- **Tests:** `tests/test_agent_prompt_registry.py` (dedup por sha, fs_scan, diff) + extensión de los tests de runner (mock del agent file → metadata con sha esperado).
- **Complejidad:** M.

---

#### V1.2 Smart dispatch v1 — recomendación de runtime+modelo

- **Ataca:** D2. Depende de V0.4 (mejor señal) pero puede salir sin él.
- **Objetivo:** que Stacky recomiende (no imponga) runtime y modelo usando los datos que ya recolecta. El dev ve el formulario pre-cargado con la mejor opción y un "por qué".
- **Diseño:**
  - Nuevo `backend/services/run_advisor.py`:
    ```python
    @dataclass(frozen=True)
    class Advice:
        runtime: str; model: str | None; reason: str; confidence: str  # "high"|"low"|"default"
    def advise(*, agent_type: str, project: str | None,
               context_blocks: list[dict] | None = None) -> Advice
    ```
    Reglas deterministas, SIN LLM:
    1. Candidatos = runtimes en `CAPABILITIES` con datos en `harness_health.compute_health(days=14)` para ese `agent_type` (y proyecto si hay desglose).
    2. Score por candidato = éxito-sin-intervención (peso 3) − autocorrection_rate (peso 1) − costo normalizado (peso 1); mínimo de 5 runs para puntuar.
    3. Sin datos suficientes → `Advice(runtime="github_copilot"-o-default-actual, confidence="default", reason="sin historial suficiente")`.
    4. Modelo: delega en `llm_router.decide(...)` (el clamp existente aplica solo).
  - Endpoint: `GET /api/agents/advise?agent_type=X&ticket_id=N` → Advice serializado.
  - Flag: `STACKY_RUN_ADVISOR_ENABLED` (bool, default false; el preset `full` de V0.1 lo enciende) + entrada en `FLAG_REGISTRY`.
  - Frontend: en el modal de lanzar agente, si el flag está ON, llamar `advise` al abrir y preseleccionar runtime/modelo con tooltip `reason`. El operador siempre puede cambiar. **v1 nunca fuerza** (enforcement es V2.2).
- **Criterios de aceptación:** con historial sintético donde codex tiene 90% éxito y claude 50% para `developer`, advise recomienda codex con reason que menciona las métricas; con < 5 runs → confidence "default"; flag OFF → el frontend no llama; el modelo recomendado jamás supera el cap (clamp).
- **Tests:** `tests/test_run_advisor.py` con fixtures de health (reusar helpers `_mk_cli_exec` de `test_harness_health.py`): dominancia clara, empate→default, sin datos, respeto de capabilities.
- **Complejidad:** M.

---

#### V1.3 Contrato universal de outputs file-based (intake con reparación)

- **Ataca:** D6 (y la causa raíz del bug histórico "crea archivos pero no la task").
- **Objetivo:** que TODO output que entra por archivos pase por un único punto de validación+reparación antes de encolarse a ADO — la misma garantía que los `submit_*` MCP dan a claude, para codex y cualquier runtime futuro sin MCP.
- **Diseño:**
  - Nuevo `backend/services/artifact_intake.py` (dueño único):
    ```python
    @dataclass(frozen=True)
    class IntakeResult:
        ok: bool; normalized: dict | str | None
        repaired: bool; repairs: list[str]      # ["stripped_code_fence", ...]
        errors: list[str]                       # legibles por el autocorrect loop
    def validate_and_normalize(*, raw: str, kind: str,  # "pending_task_json" | "comment_html"
                               ticket_context: dict | None = None) -> IntakeResult
    ```
    Pipeline interno para JSON: (1) reparaciones seguras y deterministas — strip de code fences, BOM, comillas tipográficas, comas finales, texto antes/después del primer `{`/último `}` balanceado; (2) `json.loads`; (3) validación con `artifact_validator` (reuso, no duplicar reglas); (4) **regla anti-ordinal**: si el payload referencia ids de tareas/parents, deben existir en `ticket_context` (ids reales de ADO, no ordinales 1..N) — si no, error explícito `"parent_id N no existe en el ticket; usar el id ADO real"`. Para HTML: validación existente del validator, sin reparaciones agresivas.
  - Cableado: `services/output_watcher.py` y `services/agent_completion.py` reemplazan su parseo directo por `artifact_intake.validate_and_normalize(...)`. `ok=True` → encolar en `ado_write_outbox` como hoy (con `normalized`, no el raw). `ok=False` → la execution pasa a `needs_review` con `metadata["intake_errors"] = errors` y `failure_kind="contract_failed"` (V0.4) — **nunca** llega a ADO un artefacto inválido ni se descarta en silencio.
  - Sinergia con autocorrección: el loop de codex (H2.3, `codex_autocorrect.run_autocorrect_loop`) recibe `IntakeResult.errors` como feedback de reintento (los errores se redactan para ser accionables por el modelo).
  - Flag: `STACKY_ARTIFACT_INTAKE_ENABLED` (default false; preset `full` ON; mientras esté OFF, el watcher usa el path actual — rollout sin riesgo).
- **Criterios de aceptación:** JSON con fence+coma final → reparado, validado, encolado, `repaired=true` con la lista de reparaciones en metadata; JSON irreparable → needs_review con errores legibles y NADA encolado; payload con `parent_id` ordinal (no presente en el contexto) → error anti-ordinal específico; HTML válido pasa intacto; flag OFF → comportamiento actual byte-idéntico.
- **Tests (TDD primero):** `tests/test_artifact_intake.py` — tabla de ≥10 payloads rotos→esperado (incluir el payload real del incidente doc 20 como caso de regresión); integración watcher→intake→outbox con flag ON/OFF.
- **Complejidad:** M.

---

#### V1.4 CI mínima + saneo incremental de la suite

- **Ataca:** D7. Divisible en 3 sub-ítems independientes.
- **Diseño:**
  - **a) Runner por archivo (S):** `backend/scripts/run_harness_tests.ps1` (+ `.sh`): lista curada `HARNESS_TEST_FILES` (los `test_harness_*.py`, `test_codex_*.py`, `test_cli_*.py`, `test_model_policy.py`, `test_evals_*.py`, `test_run_*.py` y los nuevos de este plan); ejecuta `python -m pytest <archivo> -q` UNO POR UNO (esquiva la polución); exit 1 si cualquiera falla; resumen final archivo→estado.
  - **b) Workflow CI (S, depende de a):** `.github/workflows/ci.yml`: jobs en ubuntu-latest con Python pineado — (1) `harness-tests`: ejecuta el runner (a); (2) `evals`: `cd backend && python -m evals run all`. Trigger: PR + push a main. Sin servicios externos (sqlite y filesystem alcanzan).
  - **c) Saneo de polución (L, incremental):** causa raíz = engine sqlite in-memory compartido + singletons de app entre módulos. Estrategia: fixture de aislamiento en `conftest.py` (engine por test con `StaticPool` + `create_all`/`dispose`, reset de los singletons conocidos) aplicada módulo a módulo con marker `@pytest.mark.isolated`; cada módulo saneado se suma a `HARNESS_TEST_FILES`. NO intentar arreglar los 449 errores de una vez: ratchet (la lista solo crece, CI impide que se encoja).
- **Criterios de aceptación:** (a) corre verde local en HEAD; (b) PR con un test del arnés roto falla el workflow; PR que rompe un golden falla el job evals; (c) cada módulo migrado pasa tanto aislado como dentro de la suite curada.
- **Tests:** el ítem ES tests; criterio = workflow verde reproducible 3 ejecuciones seguidas.
- **Complejidad:** a=S, b=S, c=L (incremental, sin fecha de fin — ratchet).

---

#### V1.5 Memoria colaborativa Fase B — consolidación estructural (B5)

- **Ataca:** D9.
- **Objetivo:** garantía estructural (no por convención) de que un conocimiento sale por UN solo canal. Scope mínimo aquí; el detalle vive en el plan v2 de memoria (`docs/plans/plan-memoria-colaborativa-stacky-agents-2026-06-06-v2.md`, raíz del repo) — esta entrada lo referencia para que la hoja de ruta quede completa, no lo reescribe.
- **Diseño (resumen):**
  - Allowlist estructural de types en `services/memory_store.py`: `INJECTABLE_TYPES = frozenset({"session_summary", ...})`; `get_context_for_run` filtra por ella; `POST /api/memory` rechaza con 400 los types reservados a FA-* (`decision`, `anti_pattern`, `glossary`, `style`).
  - Test de no-doble-inyección: e2e que arma system prompt (compose/cli knowledge) + user prompt (enrich_blocks) y asserta intersección vacía de contenidos.
- **Criterios de aceptación:** POST con type reservado → 400; `get_context_for_run` nunca devuelve types fuera de la allowlist aunque existan filas; test e2e de no-duplicación verde.
- **Tests:** extensión de `tests/test_memory_*.py` existentes + el e2e nuevo.
- **Complejidad:** M.

---

### FASE V2 — Diferenciales: el arnés como plataforma (M/L)

---

#### V2.1 Runtime Conformance Suite + kit de onboarding de runtime

- **Ataca:** la dimensión model-agnostic completa (consolida D2/D6 a futuro).
- **Objetivo:** que agregar un runtime nuevo (Gemini CLI, futuro proveedor X) sea: implementar un contrato conocido + pasar una suite. El arnés deja de ser "features cableadas a 2 CLIs" y pasa a ser plataforma.
- **Diseño:**
  - `backend/tests/conformance/test_runtime_conformance.py`: parametrizado por runtime declarado en `CAPABILITIES`. Con dobles (sin binarios reales), verifica para cada runtime:
    1. El runner invoca `harness.post_run.finalize_run` en el path de éxito.
    2. Telemetría persistida vía `harness.telemetry.persist` con `runtime` correcto.
    3. Claves canónicas de metadata presentes y NO renombradas (`runtime`, session key según `harness/resume.py::_SESSION_KEY`, `contract_result`, `failure_kind` si error).
    4. `harness.resume.resolve` integrable si `supports_resume`.
    5. RunawayGuard cableado (turnos siempre; costo si la telemetría lo trae).
    6. Inyecciones (skills/memoria/knowledge/egress) presentes según flags, vía los seams compartidos (`context_enrichment`, `stacky_skills`).
    7. `write_repro_script` o equivalente genera artefacto reproducible en run_dir.
  - `docs/23_CHECKLIST_NUEVO_RUNTIME.md`: pasos exactos (entrada en `CAPABILITIES` → claves en `harness/resume.py` → flags + `FLAG_REGISTRY` → runner usando los seams → conformance verde → entrada en presets V0.1). El checklist referencia la suite: "terminaste cuando conformance pasa parametrizado con tu runtime".
- **Criterios de aceptación:** la suite pasa hoy para `claude_code_cli` y `codex_cli` (y los puntos aplicables de `github_copilot`); quitar artificialmente el cableado de runaway de un runner la hace fallar (test del test); el checklist permite a un dev junior portar un runtime dummy "echo" de punta a punta en < 1 día.
- **Tests:** la suite ES el deliverable; agregar dummy runtime `echo_cli` de fixture para probar la parametrización.
- **Complejidad:** M.

---

#### V2.2 Smart dispatch v2 — auto-routing con presupuesto

- **Ataca:** D2 (cierre) + gobierno de costo end-to-end. Depende de V1.2, V0.4, V0.5, V1.1.
- **Objetivo:** el operador define presupuesto y políticas; Stacky elige runtime+modelo y degrada solo.
- **Diseño:**
  - Flags: `STACKY_RUN_ADVISOR_ENFORCE` (bool, default false) y `STACKY_BUDGET_PER_TICKET_USD` (float, 0.0=sin límite) en config + `FLAG_REGISTRY`.
  - En el launch (`api/agents.py`): si enforce ON y el payload no trae runtime explícito → usar `run_advisor.advise(...)`. Si trae explícito, respetar (el humano siempre gana).
  - Presupuesto: suma de costos (reales+estimados, V0.5) de executions del ticket; si `costo_acumulado + estimación_del_run > budget` → degradar modelo un escalón (sonnet→haiku, vía `model_policy`) y registrar `metadata["budget_degraded"]=true`; si aún excede → 402 `{"error":"budget_exceeded", "spent": X, "budget": Y}` con override `force_budget=true`.
  - Señal de aprendizaje: el advisor pondera `failure_kinds` (V0.4) y puede excluir un `prompt_sha` (V1.1) con regresión confirmada por evals.
- **Criterios de aceptación:** enforce OFF = comportamiento v1; ticket con presupuesto agotado degrada y luego bloquea con 402; override explícito documentado en metadata; nunca se supera el cap de modelo existente.
- **Tests:** `tests/test_run_advisor_enforce.py` — matriz enforce×budget×override; degradación de modelo verificada contra `model_policy`.
- **Complejidad:** L.

---

#### V2.3 Ciclo de mejora continua de prompts (golden loop)

- **Ataca:** D5/D7 (lado calidad). Depende de V1.1; reusa H6.
- **Objetivo:** que cada run bueno pueda convertirse en regresión permanente y cada cambio de prompt se mida contra la historia.
- **Diseño:**
  - **Promote-to-golden:** botón en la UI de execution (estado `completed`) → `POST /api/evals/promote {execution_id}` → reusa `evals/harvest.py` (con `redact_irreversible` de `pii_masker`, ya validado en H6) para escribir el golden en `evals/agents/<agent_type>/`.
  - **Evals programados:** daemon thread en `app.py` (mismo patrón que el reaper de `app.py:273`) que corre `evals run all` cada `STACKY_EVALS_INTERVAL_HOURS` (default 0=off) y persiste resultados en tabla nueva `eval_runs` (id, ran_at, agent_type, passed, failed, scores_json, prompt_sha si disponible).
  - **Gate de import endurecible:** el gate suave de H6 (`api/agents.py:119`) gana modo configurable: `STACKY_EVAL_GATE_MODE` = `off|warn|block` (default `warn`). `block` → si los goldens del agent_type fallan con el prompt nuevo, el import devuelve 409 con el detalle (el archivo NO se pisa).
  - **Tendencia:** `GET /api/metrics/eval-history?agent_type=X` → series para correlacionar score con `prompt_sha` (V1.1).
- **Criterios de aceptación:** promote genera golden válido y redactado (sin PII); el daemon respeta intervalo 0=off; modo block rechaza un import que rompe goldens y modo warn solo loguea; la historia correlaciona por prompt_sha.
- **Tests:** `tests/test_evals_promote.py`, `tests/test_eval_gate_modes.py`, extensión de `test_evals_harvest.py`.
- **Complejidad:** M.

---

#### V2.4 Cache/dedup de runs CLI

- **Ataca:** D10. Depende de V1.1 (prompt_sha).
- **Objetivo:** no pagar dos veces por el mismo trabajo.
- **Diseño:** en el launch, calcular `run_fingerprint = sha256(prompt_sha + model + normalize(context_blocks))`; buscar `AgentExecution` `completed` con el mismo fingerprint (clave nueva `metadata["run_fingerprint"]`, sellada por los runners) en ventana `STACKY_RUN_CACHE_DAYS` (default 0=off). Si hay hit → la respuesta 202 incluye `{"cached_candidate": exec_id}` y el frontend ofrece "Reusar resultado de #N (ahorra ~$X)". **Nunca** auto-skip: el operador decide.
- **Criterios de aceptación:** mismo fingerprint en ventana → candidate presente; cualquier cambio de contexto/prompt/modelo → sin candidate; default off byte-idéntico al actual.
- **Tests:** `tests/test_run_fingerprint.py` (normalización estable de blocks, ventana, off).
- **Complejidad:** S/M.

---

#### V2.5 Paridad codex MCP (H2.5 diferido — condicional)

- **Ataca:** D6 (cierre definitivo para codex).
- **Gate de entrada:** binario `codex` disponible en el entorno de dev con soporte MCP verificado. Hasta entonces, V1.3 es la red de seguridad.
- **Diseño:** habilitar `supports_mcp=True` en `CAPABILITIES`, generar `--mcp-config` efímero reusando `services/stacky_mcp.py` (mismo server JSON-RPC stdio), y al activarlo retirar el path file-based PARA CODEX (los `submit_*` pasan a ser el canal). Conformance suite (V2.1) valida la integración.
- **Complejidad:** M (cuando el gate se cumpla).

---

## 4. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | V0.1 Perfiles de arnés | S | Muy alto (activa TODO lo construido) | Bajo (flags ya hot-apply) | — |
| 2 | V0.2 Guard duplicados | S | Alto | Bajo | — |
| 3 | V0.3 Cap concurrencia | S | Alto | Bajo | — |
| 4 | V0.4 Failure taxonomy | S | Alto (habilita data-driven) | Bajo (clave nueva) | — |
| 5 | V0.5 Pricing fallback | S | Alto (completa el KPI económico) | Bajo | — |
| 6 | V1.4a+b CI mínima | S+S | Muy alto (protege todo lo demás) | Bajo | — |
| 7 | V1.1 Versionado prompts | M | Muy alto (activo principal con historia) | Bajo (tabla nueva) | — |
| 8 | V1.3 Intake universal | M | Muy alto (mata la clase de bug histórica) | Medio (tocar watcher → flag OFF default) | V0.4 |
| 9 | V1.2 Advisor v1 | M | Alto | Bajo (solo recomienda) | V0.4, V0.5 |
| 10 | V1.5 Memoria Fase B | M | Medio/Alto | Medio (contratos de memoria) | plan v2 memoria |
| 11 | V2.1 Conformance suite | M | Alto (plataforma) | Bajo (solo tests+doc) | V0.4 |
| 12 | V2.3 Golden loop | M | Alto | Bajo | V1.1 |
| 13 | V2.4 Run cache | S/M | Medio | Bajo | V1.1 |
| 14 | V2.2 Advisor v2 enforce | L | Alto | Medio | V1.2, V0.5, V1.1 |
| 15 | V1.4c Saneo suite (ratchet) | L | Medio (continuo) | Bajo | V1.4a |
| 16 | V2.5 Codex MCP | M | Alto | Medio | gate externo (binario) |

**Reglas de implementación para el dev agéntico (aplican a TODOS los ítems):**
1. TDD: test que falla por la razón correcta → cambio mínimo → verde → refactor solo si reduce riesgo.
2. Validar por archivo de test, nunca por suite completa (polución conocida). Si se toca un contrato compartido, baseline por `git stash` antes/después.
3. Todo flag nuevo: `config.py` + `FLAG_REGISTRY` + preset correspondiente (V0.1) en el MISMO PR.
4. Metadata: solo claves nuevas; jamás renombrar `runtime`, `session_id`, `codex_session_id`, `contract_result`, `claude_telemetry`, `runaway`.
5. Default de todo lo nuevo = OFF/0 (retro-compat byte-idéntica); el encendido es vía perfiles.
6. Ningún path nuevo publica en ADO directo: siempre `ado_write_outbox`.
7. Errores de runner son errores reales: prohibido fallback silencioso entre runtimes.

---

## 5. Por qué esto hace que Stacky gane vs usar agentes sueltos por fuera

El argumento, capa por capa (cada bullet cita la capacidad que lo sostiene):

1. **Garantía de artefactos, no esperanza.** Un CLI suelto produce texto que alguien copia a ADO a mano y reza. Stacky valida server-side (artifact_validator + `submit_*` MCP + intake V1.3 con reparación determinista y regla anti-ordinal), y publica con outbox idempotente, backoff y dead-letter: **lo que el agente produce llega válido, exactamente una vez, o queda en needs_review con diagnóstico accionable**. La clase entera de bugs "creó archivos pero no la task" deja de existir por construcción.
2. **Cada run arranca senior, en cualquier proveedor.** Skills, memoria colaborativa, knowledge del proyecto, client profile y reglas de contrato se inyectan uniformemente en claude, codex y copilot (seams únicos: `context_enrichment`, `stacky_skills`, `harness/run_contract`), con budget de contexto para no desbordar. Por fuera, ese contexto se re-escribe a mano en cada sesión y se pierde al cerrar la terminal. Con V1.5 además se garantiza sin duplicación.
3. **Economía visible y gobernada.** Telemetría normalizada multi-proveedor + pricing fallback (V0.5) + KPIs por runtime/proyecto + runaway guard + cap duro de modelo + presupuesto por ticket (V2.2): el operador sabe cuánto cuesta cada ticket, qué runtime rinde más para cada tipo de agente (advisor V1.2), y ningún run puede quemar dinero sin techo. Los CLIs sueltos no suman costo entre sí ni se auto-limitan.
4. **Resiliencia operacional de plataforma.** Reaper + heartbeat + resume multi-runtime + repro.ps1 + guard de duplicados + cap de concurrencia (V0.2/V0.3): un crash no deja zombies, un retry no duplica publicaciones, todo run es reproducible. Nada de esto existe usando agentes a mano.
5. **El sistema mejora con cada run; los agentes sueltos no acumulan nada.** Evals golden + promote-to-golden + versionado de prompts con diff y correlación score↔versión (V1.1+V2.3) + taxonomía de fallos alimentando el dispatch (V0.4→V2.2): cada run bueno se vuelve regresión permanente, cada fallo se vuelve dato de routing, cada cambio de prompt se mide antes de pisarlo. Es un volante de inercia que los CLIs por separado no pueden tener — y la conformance suite (V2.1) extiende todo esto a cualquier proveedor futuro al costo de pasar una suite de tests.

La síntesis: **invisible para el dev** (elige perfil `full` una vez; lanza agentes como siempre; el formulario ya viene pre-cargado con la mejor opción), **visible en resultados** (artefactos válidos en ADO, costo por ticket en el dashboard, menos re-runs, prompts que mejoran de forma medible).

---

## 6. Métricas de éxito del plan (medibles en `harness-health`)

| Métrica | Hoy | Objetivo post-V1 |
|---|---|---|
| Runs con costo conocido (`runs_with_cost`/total) | solo claude | 100% (reportado o estimado) |
| Artefactos inválidos llegados a ADO | posible (path codex) | 0 por construcción |
| Runs duplicados accidentales | sin guard | 0 (409 + force explícito) |
| Fallos clasificados (`failure_kind`) | 0% | 100% de errores nuevos |
| Regresión de arnés detectada antes de merge | manual | CI en cada PR (tests curados + evals) |
| Runs con `prompt_sha` trazable | 0% | 100% de runs CLI nuevos |
| Flags para activar el arnés completo | 26 toggles | 1 perfil |
