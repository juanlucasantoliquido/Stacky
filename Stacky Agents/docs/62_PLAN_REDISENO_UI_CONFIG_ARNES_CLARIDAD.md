# Plan 62 — Rediseño de la UI de Configuración del Arnés (claridad e intuición)

> **Versión: v1 → v2** (endurecido por el juez adversarial `criticar-y-mejorar-plan`).
>
> **CHANGELOG v2:**
> - **C1 (IMPORTANTE) — señal de default honesta + lista curada completada por evidencia.**
>   El `default` declarado mentía: ≥5 flags que arrancan ON de fábrica en `config.py`
>   (`STACKY_EPIC_FROM_BRIEF_ENABLED`, `STACKY_EXECUTION_TRACE_ENABLED`,
>   `STACKY_ORPHAN_REAPER_ENABLED`, `STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED`,
>   `STACKY_RUNNER_REAP_ON_CLOSE_ENABLED`) NO estaban en la lista de 7 → la UI las pintaba
>   "def: OFF" + borde "modificado" estando en su valor de fábrica, engañando al operador
>   (lo opuesto al KPI). **[ADICIÓN ARQUITECTO]**: (a) se expande la lista curada con esas
>   5 keys confirmadas contra `config.py`; (b) el badge `def:` se muestra SOLO cuando el
>   default es conocido con confianza (`default_known`); (c) el resaltado per-flag se
>   reformula de "modificado/fuera de default" (claim sobre el default real, no conocido)
>   a **"activa / con valor"** (`value != type-zero`, literalmente cierto sin conocer el
>   default de fábrica). Ver F0/F3/F4.
> - **C2 (IMPORTANTE) — gate binario real.** vitest NO está instalado en el entorno
>   (memoria `backend-dev-test-env`). El criterio de aceptación binario de F2-F5 es
>   `npx tsc --noEmit` = 0 errores; los `.test.tsx` se escriben y se corren cuando el
>   toolchain esté (no bloqueante). Ya no se declara "vitest verde" como gate vinculante.
> - **C3 (MENOR) — semántica del contador.** El contador de sección separa explícitamente
>   "N activas" (bools en true) de "M con valor" (no-bools con `value != type-zero`); ya no
>   se mezclan en una sola métrica ambigua.
> - **C4 (MENOR) — comparación numérica normalizada** en el predicado de "con valor"
>   (evita falsos positivos por formateo `1` vs `1.0`).
> - **C5 (MENOR) — anclar por SÍMBOLO, no por línea cruda.** Las ediciones del frontend se
>   localizan por símbolo (`GROUP_LABELS`, el `useMemo` de groups, el render `.map(group =>`)
>   y se confirman con grep antes de editar (los rangos de línea son orientativos y driftearon:
>   la lógica de `flag.group` vive ~`HarnessFlagsPanel.tsx:213-217,262-263`).
> - **C6 (MENOR) — descubribilidad del acoplamiento ratchet.** Comentario en la cabecera de
>   `FLAG_REGISTRY` apuntando a `_CATEGORY_KEYS` para que un plan futuro que agregue una flag
>   sepa que también debe categorizarla (si no, el ratchet rompe CI a propósito).
> - **CONFIRMADO (no era defecto):** la enumeración de `_CATEGORY_KEYS` es EXACTA y COMPLETA
>   (142/142 keys, 0 huérfanas, 0 stale, 0 colisiones — verificado contra el registry). Las
>   descripciones inline REUSAN `flag.description` del registry (no se inventa texto). La
>   alternativa "derivar categoría del `group` crudo" se RECHAZA: `group="global"` es el
>   basurero de ~100 flags y reproduciría el problema que este plan resuelve.

## 1. Objetivo + KPI

**Objetivo (un párrafo).** Rediseñar el panel de configuración del arnés
(`HarnessFlagsPanel`) para que deje de ser una lista plana kilométrica de ~142 flags
y pase a ser una pantalla **categorizada, colapsable, con ayuda contextual rica,
defaults visibles, estado on/off claro y búsqueda/filtrado**. Una persona con poca
experiencia técnica debe poder entender qué hace cada opción y configurarla con
confianza. El cambio es **puramente de presentación + serialización aditiva**: NO crea
flags nuevas, NO cambia la semántica de ninguna flag, NO toca el pipeline de ejecución
de ningún runtime, y NO agrega trabajo al operador.

**KPI / impacto esperado:**
- **Tiempo para encontrar y entender una flag**: de "scroll por 142 ítems sin saber qué
  es cada uno" a "abrir 1 de ~13 categorías + leer descripción inline" (objetivo: <15s).
- **Claridad**: 100% de las flags muestran su descripción **inline** (hoy solo aparece
  en un `?` con `title` nativo, `HarnessFlagsPanel.tsx:141`), su **valor actual** y su
  **estado** (activa/con-valor). Las flags con **default conocido con confianza** muestran
  además un badge `def: ON/OFF`. (v2/C1: NO se afirma un default falso para las flags cuyo
  default de fábrica no está confirmado — honestidad por sobre cobertura cosmética.)
- **Navegabilidad**: ≤13 secciones colapsables vs. la lista única actual; cada flag
  pertenece a exactamente 1 categoría (test bidireccional lo garantiza).
- **Cero regресión**: los consumidores actuales del endpoint `/api/harness-flags`
  siguen funcionando byte-compatibles (solo se AGREGAN campos al JSON).

## 2. Por qué ahora / gap que cierra

Los planes 48–61 agregaron decenas de flags al arnés (gates, convergencia, descomposición,
task gate, aprendizaje bidireccional, especulación). El `FLAG_REGISTRY` de
`services/harness_flags.py` ya tiene **~142 entradas** (verificado: archivo de 1569 líneas,
último flag `STACKY_ADO_SERVICE_IDENTITY` en `harness_flags.py:1447`). Pero la UI quedó
estancada en el diseño del Plan 33:

- `HarnessFlagsPanel.tsx:211-227` agrupa **solo por `flag.group`** y
  `HarnessFlagsPanel.tsx:16-20` solo conoce labels de **3 grupos** (`claude_code_cli`,
  `codex_cli`, `global`). El registry usa además `database`, `observability`, `agents`,
  `context`, `preflight` (ej. `harness_flags.py:1057,1069,1082,1094,1185`), que el panel
  **dumpea como claves crudas** sin label ni orden (`HarnessFlagsPanel.tsx:263`,
  `GROUP_LABELS[group] ?? group`).
- El grupo `global` es un **basurero de ~100 flags** sin subdivisión → lista interminable.
- La descripción de cada flag (riquísima en el registry) **solo se ve en hover** sobre un
  `?` (`HarnessFlagsPanel.tsx:141`, atributo `title`). No hay ayuda inline, ni default
  visible, ni búsqueda, ni jerarquía visual.

Este plan cierra el gap de **DX/comprensión** sin tocar la lógica del arnés. Es la
contraparte de presentación a toda la potencia que ya existe.

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** este plan **no toca el pipeline de ejecución**. Las flags
  conservan su semántica idéntica en Codex CLI, Claude Code CLI y GitHub Copilot Pro.
  Impacto por runtime: **ninguno** (solo cambia cómo se presentan en la UI). No hay
  fallback por runtime porque no hay código de runtime involucrado.
- **Cero trabajo extra para el operador:** no se crean flags nuevas ni nueva config a
  cargar. La mejora es de navegación/lectura. Backward-compatible.
- **Human-in-the-loop:** el operador sigue siendo quien decide cada flag; mejoramos su
  capacidad de entender qué activa. No hay autonomía nueva.
- **Mono-operador sin auth real:** no se agrega RBAC ni multiusuario.
- **No degradar:** el endpoint solo AGREGA campos al JSON (aditivo); el frontend reusa
  React Query + el endpoint existente. Sin nuevas dependencias. Sin cambios de performance.
- **Regla dura de config-por-UI:** toda flag editable sigue editándose por UI (no se quita
  ninguna del panel; se reorganizan y se documentan mejor).

## 4. Fases

> **Orden de dependencia:** F0 → F1 → F2 → F3 → F4 → F5. F0/F1 son backend (sirven datos);
> F2 es el contrato de tipos; F3/F4/F5 son frontend. Cada fase es verificable sola.

> **Intérprete de tests backend (úsalo en todos los comandos pytest):** el venv del backend.
> Comando base (PowerShell):
> `& "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest <archivo> -q`
> ejecutado desde `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend`. Si el venv está en otra
> ruta, usá el intérprete que ya corre el resto de `tests/test_harness_flags.py` (ver CLAUDE.md).

---

### F0 — Backend: taxonomía de categorías + `default` declarado (PURO, aditivo)

**Objetivo (1 frase).** Enriquecer `FlagSpec` y `read_current()` con una **categoría**
curada y un **default declarado** por flag, sin romper consumidores ni cambiar
comportamiento. **Valor:** habilita toda la UX nueva con datos servidos desde una única
fuente de verdad.

**Archivo a editar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/services/harness_flags.py`

**Símbolos exactos a crear/editar:**
- Editar la dataclass `FlagSpec` (línea 18): agregar **dos campos opcionales al final**
  (deben ir al final y con default para no romper las ~142 llamadas posicionales/keyword
  existentes):
  ```python
  @dataclass(frozen=True)
  class FlagSpec:
      key: str
      type: str
      label: str
      description: str
      group: str
      pair: str | None = None
      env_only: bool = False
      default: object | None = None   # NUEVO — default DECLARADO (hint de UI). None = usar type-zero.
  ```
  (NO se agrega `category` como campo de `FlagSpec`; la categoría se resuelve por una
  estructura externa `_CATEGORY_KEYS` para no editar las 142 entradas — ver abajo.)

- Crear una dataclass `CategorySpec` y la tupla ordenada `FLAG_CATEGORIES` (después de
  `FlagSpec`, antes de `FLAG_REGISTRY`):
  ```python
  @dataclass(frozen=True)
  class CategorySpec:
      id: str          # slug estable (no cambia)
      label: str       # título humano para la UI (español)
      description: str # 1 línea: qué controla esta categoría

  FLAG_CATEGORIES: tuple[CategorySpec, ...] = (
      CategorySpec("runtimes_cli", "Runtimes CLI (Claude / Codex)",
          "Comportamiento de los agentes que corren como CLI: gates de contrato, autocorrección, hooks, resume, MCP, modelos."),
      CategorySpec("contexto_memoria", "Contexto y memoria",
          "Qué información recibe el agente: presupuesto/dedup/rerank de contexto, memoria colaborativa, skills, few-shot, catálogo."),
      CategorySpec("calidad_verificacion", "Calidad y verificación del entregable",
          "Criterios de aceptación, verificación ejecutable, contrato de aceptación, anti-verde-falso, convergencia, self-review, esfuerzo."),
      CategorySpec("integridad_grounding", "Integridad y grounding del resultado",
          "Verifica que lo que el agente afirma sea real: precondiciones, verificación post-create de tasks, anclado de referencias."),
      CategorySpec("epicas_ado", "Épicas, briefs y publicación en ADO",
          "Generación, saneamiento, gates, preview, descomposición y selector de modelo de épicas/issues hacia Azure DevOps."),
      CategorySpec("flujo_funcional", "Flujo funcional (Tasks)",
          "Creación de Tasks funcionales en ADO y su gate determinista."),
      CategorySpec("routing_costo", "Routing de modelo y costo",
          "Estimación de complejidad, routing por dificultad, advisor de runtime, presupuesto por ticket, caché de runs, evals."),
      CategorySpec("fiabilidad_ciclo_vida", "Fiabilidad y ciclo de vida del run",
          "Higiene de procesos: reaping, watchdog, validación pending-task, idempotencia, retries, runaway guard, auto-reparación, intake."),
      CategorySpec("observabilidad_notif", "Observabilidad y notificaciones",
          "KPIs en harness-health, historial, footer ADO, webhooks, notificaciones, telemetría en vivo, salud operativa, pipelines, trazabilidad."),
      CategorySpec("aprendizaje", "Aprendizaje y memoria que empuja",
          "Rechazos como anti-patrones, nota del operador a memoria, aprendizaje desde ediciones humanas en ADO."),
      CategorySpec("preflight_intencion", "Pre-vuelo de intención",
          "Brief de intención negociable que el operador aprueba antes del run."),
      CategorySpec("base_datos", "Base de datos y caché ADO",
          "Directiva de acceso read-only a la BD, caché y pre-warm de lecturas caras de ADO."),
      CategorySpec("avanzado", "Avanzado / experimental",
          "Kill-switches internos y features beta: egress check, especulación anticipatoria."),
      CategorySpec("otros", "Otros / sin categorizar",
          "Flags aún no asignadas a una categoría (no debería haber ninguna; el test lo garantiza)."),
  )
  ```

- Crear el mapa **ordenado** `_CATEGORY_KEYS: dict[str, tuple[str, ...]]` (única fuente de
  verdad de la asignación flag→categoría). Contenido EXACTO (transcribir tal cual):

  ```python
  _CATEGORY_KEYS: dict[str, tuple[str, ...]] = {
      "runtimes_cli": (
          "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED", "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED",
          "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES", "CLAUDE_CODE_CLI_HOOKS_ENABLED",
          "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED", "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_PROJECTS",
          "CLAUDE_CODE_CLI_RESUME_ENABLED", "CLAUDE_CODE_CLI_RESUME_PROJECTS",
          "CLAUDE_CODE_CLI_MCP_ENABLED", "CLAUDE_CODE_CLI_MCP_PROJECTS",
          "CODEX_CLI_CONTRACT_GATE_ENABLED", "CODEX_CLI_AUTOCORRECT_ENABLED",
          "CODEX_CLI_AUTOCORRECT_MAX_RETRIES", "CODEX_CLI_MODEL_DENYLIST",
          "CODEX_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_PROJECTS",
      ),
      "contexto_memoria": (
          "STACKY_CONTEXT_BUDGET_ENABLED", "STACKY_CONTEXT_BUDGET_PROJECTS",
          "STACKY_CONTEXT_BUDGET_TOKENS", "STACKY_CONTEXT_DEDUP_ENABLED",
          "STACKY_CONTEXT_DEDUP_PROJECTS", "STACKY_CONTEXT_RERANK_ENABLED",
          "STACKY_PARALLEL_INJECTORS_ENABLED", "STACKY_RETRIEVAL_EXPANSION_ENABLED",
          "STACKY_MEMORY_INJECTION_ENABLED", "STACKY_MEMORY_INJECTION_PROJECTS",
          "STACKY_MEMORY_CAPS_JSON", "STACKY_MEMORY_REVIEW_SWEEP_HOURS",
          "STACKY_MEMORY_DIRECTIVE_MAX_CHARS", "STACKY_MEMORY_INJECT_SCOPES",
          "STACKY_SKILLS_ENABLED", "STACKY_SKILLS_PROJECTS",
          "STACKY_CLI_FEWSHOT_ENABLED", "STACKY_CLI_FEWSHOT_K", "STACKY_CLI_FEWSHOT_PROJECTS",
          "STACKY_INJECT_PROCESS_CATALOG", "STACKY_CAPS_ADVISOR_ENABLED",
      ),
      "calidad_verificacion": (
          "STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED", "STACKY_ACCEPTANCE_CRITERIA_PROJECTS",
          "STACKY_CRITERIA_REPAIR_ENABLED", "STACKY_CRITERIA_REPAIR_MAX_RETRIES",
          "STACKY_SELF_REVIEW_MODE", "STACKY_SELF_REVIEW_MIN_SCORE",
          "STACKY_EXEC_VERIFICATION_ENABLED", "STACKY_EXEC_VERIFICATION_MODE",
          "STACKY_EXEC_VERIFICATION_TIMEOUT_S", "STACKY_EXEC_VERIFICATION_BUDGET_S",
          "STACKY_EXEC_VERIFICATION_PROJECTS", "STACKY_EXEC_REPAIR_ENABLED",
          "STACKY_EXEC_REPAIR_MAX_RETRIES", "STACKY_FAKE_GREEN_GUARD_ENABLED",
          "STACKY_FAKE_GREEN_GUARD_HARD", "STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED",
          "STACKY_ACCEPTANCE_CONTRACT_ENABLED", "STACKY_ACCEPTANCE_CONTRACT_MODE",
          "STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS", "STACKY_ACCEPTANCE_CONTRACT_PROJECTS",
          "STACKY_ACCEPTANCE_GATE_ENABLED", "STACKY_ACCEPTANCE_REPAIR_ENABLED",
          "STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES", "STACKY_ACCEPTANCE_INTEGRITY_ENABLED",
          "STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED", "STACKY_QUALITY_CONVERGENCE_ENABLED",
          "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS", "STACKY_ADAPTIVE_EFFORT_ENABLED",
          "STACKY_EFFORT_FLOOR",
      ),
      "integridad_grounding": (
          "STACKY_RUN_PREFLIGHT_GATE_ENABLED", "STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED",
          "STACKY_OUTPUT_GROUNDING_ENABLED", "STACKY_OUTPUT_GROUNDING_REPAIR",
      ),
      "epicas_ado": (
          "STACKY_EPIC_FROM_BRIEF_ENABLED", "STACKY_BRIEF_MODEL_SELECT_ENABLED",
          "STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED", "STACKY_EPIC_SUMMARY_ENABLED",
          "STACKY_GROUNDING_OBSERVATORY_ENABLED", "STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED",
          "STACKY_EPIC_SANITIZE_ENABLED", "STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED",
          "STACKY_CATALOG_GROUNDING_WARNINGS_ENABLED", "STACKY_EPIC_GATE_ENABLED",
          "STACKY_EPIC_CATALOG_GATE_ENABLED", "STACKY_ADO_PREVIEW_ENABLED",
          "STACKY_EPIC_PORTFOLIO_ENABLED", "STACKY_EPIC_DECOMPOSITION_ENABLED",
          "STACKY_ADAPTIVE_SELECTOR_ENABLED", "STACKY_PROJECT_AUTOPROFILE_ENABLED",
          "STACKY_COMMENT_FULL_SCAN_ENABLED",
      ),
      "flujo_funcional": (
          "STACKY_TASK_GATE_ENABLED", "STACKY_TASK_GATE_BLOCKING",
      ),
      "routing_costo": (
          "STACKY_COMPLEXITY_ESTIMATION_ENABLED", "STACKY_DIFFICULTY_ROUTING_ENABLED",
          "STACKY_RUN_ADVISOR_ENABLED", "STACKY_RUN_ADVISOR_ENFORCE",
          "STACKY_BUDGET_PER_TICKET_USD", "STACKY_RUN_CACHE_DAYS",
          "STACKY_EVALS_INTERVAL_HOURS", "STACKY_EVAL_GATE_MODE",
          "STACKY_MAX_CONCURRENT_RUNS",
      ),
      "fiabilidad_ciclo_vida": (
          "STACKY_RUNNER_REAP_ON_CLOSE_ENABLED", "STACKY_LOG_FLUSH_INCREMENTAL_ENABLED",
          "STACKY_ORPHAN_REAPER_ENABLED", "STACKY_ORPHAN_REAPER_INTERVAL_SEC",
          "STACKY_STALL_WATCHDOG_SECONDS", "STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED",
          "STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED", "STACKY_RUNAWAY_MAX_TURNS",
          "STACKY_RUNAWAY_MAX_COST_USD", "STACKY_RUN_REPAIR_ENABLED",
          "STACKY_TRANSIENT_RUN_RETRY_ENABLED", "STACKY_TRANSIENT_RUN_RETRY_MAX",
          "STACKY_ARTIFACT_INTAKE_ENABLED", "STACKY_ARTIFACT_RESCUE_ENABLED",
      ),
      "observabilidad_notif": (
          "STACKY_RELIABILITY_KPIS_ENABLED", "STACKY_QUALITY_KPIS_ENABLED",
          "STACKY_INTEGRITY_KPIS_ENABLED", "STACKY_EXEC_VERIFICATION_KPIS_ENABLED",
          "STACKY_ACCEPTANCE_KPIS_ENABLED", "STACKY_EXECUTION_HISTORY_ENABLED",
          "STACKY_ADO_RUN_FOOTER_ENABLED", "STACKY_WEBHOOKS_V2_ENABLED",
          "STACKY_DESKTOP_NOTIFY_ENABLED", "STACKY_LIVE_TELEMETRY_ENABLED",
          "STACKY_OPERATIONAL_HEALTH_ENABLED", "STACKY_PIPELINES_ENABLED",
          "STACKY_EXECUTION_TRACE_ENABLED", "STACKY_TRACE_PROMPT_TEXT_ENABLED",
          "STACKY_DIGEST_INTERVAL_HOURS", "STACKY_ADO_FAILURE_COMMENT_ENABLED",
      ),
      "aprendizaje": (
          "STACKY_PUSH_REJECTIONS_ENABLED", "STACKY_OPERATOR_NOTE_TO_MEMORY_ENABLED",
          "STACKY_ADO_EDIT_LEARNING_ENABLED", "STACKY_ADO_EDIT_SWEEP_HOURS",
          "STACKY_ADO_SERVICE_IDENTITY",
      ),
      "preflight_intencion": (
          "INTENT_PREFLIGHT_ENABLED", "INTENT_PREFLIGHT_AUTO_APPROVE",
          "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF",
      ),
      "base_datos": (
          "STACKY_DB_READONLY_DIRECTIVE_ENABLED", "STACKY_ADO_READ_CACHE_TTL_SEC",
          "STACKY_ADO_PREWARM_ENABLED",
      ),
      "avanzado": (
          "STACKY_CLI_EGRESS_ENABLED", "STACKY_SPECULATIVE_ENABLED", "STACKY_SPECULATIVE_MODE",
      ),
      # "otros" intencionalmente vacío: es el fallback de categorize().
  }
  ```
  > **Regla de recuperación determinista (no es vaguedad, es un procedimiento exacto):**
  > el test `test_every_registry_flag_is_categorized` (F0) compara
  > `set(s.key for s in FLAG_REGISTRY)` contra `set(_KEY_CATEGORY)`. Si falla:
  > (a) una key del registry NO listada arriba → agregala a la categoría cuyo `label`
  > mejor describe su `description` en `FLAG_REGISTRY`; (b) una key listada que ya no
  > existe en el registry → eliminala de `_CATEGORY_KEYS`. No inventes categorías nuevas.

  > **v2/C6 — descubribilidad del acoplamiento.** Agregar un comentario en la línea
  > inmediatamente anterior a `FLAG_REGISTRY: tuple[FlagSpec, ...] = (` (línea 30):
  > `# NOTA: toda flag nueva debe agregarse también a _CATEGORY_KEYS (abajo) o el test`
  > `# test_every_registry_flag_is_categorized rompe CI a propósito (Plan 62).`
  > Así un plan futuro que agregue flags sabe del contrato sin investigar el fallo de CI.

- Crear el índice invertido y los helpers PUROS (después de `_REGISTRY_INDEX`, línea 1461):
  ```python
  _KEY_CATEGORY: dict[str, str] = {
      key: cat_id for cat_id, keys in _CATEGORY_KEYS.items() for key in keys
  }

  def categorize(key: str) -> str:
      """Categoría (id) de una flag. Fallback determinista a 'otros'."""
      return _KEY_CATEGORY.get(key, "otros")

  def _type_zero(flag_type: str) -> object:
      if flag_type == "bool":
          return False
      if flag_type in ("csv", "json"):
          return ""
      if flag_type == "float":
          return 0.0
      return 0  # int

  def declared_default(spec: FlagSpec) -> object:
      """Default DECLARADO para la UI. spec.default si está; si no, type-zero (= off/seguro)."""
      return spec.default if spec.default is not None else _type_zero(spec.type)

  def default_is_known(spec: FlagSpec) -> bool:
      """v2/C1 — True solo si el default fue curado con confianza (spec.default explícito).
      La UI muestra el badge 'def:' SOLO cuando esto es True, para no afirmar un default
      falso en flags cuyo default de fábrica no está confirmado contra config.py."""
      return spec.default is not None

  def is_active(spec: FlagSpec, value: object) -> bool:
      """v2/C1 — 'con valor / activa': el valor difiere de su type-zero. Claim SIEMPRE
      cierto (no depende de conocer el default de fábrica). bool→True si está en True;
      numérico→True si != 0 (comparación numérica normalizada, C4); csv/json→True si no
      vacío."""
      if spec.type == "bool":
          return bool(value)
      if spec.type in ("int", "float"):
          try:
              return float(value) != 0.0
          except (TypeError, ValueError):
              return bool(str(value).strip())
      return bool(str(value).strip())  # csv / json (string)

  def list_categories() -> list[dict]:
      """Categorías ordenadas para el frontend (id/label/description)."""
      return [{"id": c.id, "label": c.label, "description": c.description}
              for c in FLAG_CATEGORIES]
  ```

- Editar `read_current()` (línea 1464): agregar `"category"` y `"default"` al dict de cada
  flag (AGREGAR, no quitar ningún campo existente):
  ```python
  result.append({
      "key": spec.key, "type": spec.type, "label": spec.label,
      "description": spec.description, "group": spec.group, "pair": spec.pair,
      "env_only": spec.env_only, "value": value,
      "category": categorize(spec.key),            # NUEVO
      "default": declared_default(spec),            # NUEVO (hint; ver default_known)
      "default_known": default_is_known(spec),      # NUEVO v2/C1 — UI muestra badge def: solo si True
      "active": is_active(spec, value),             # NUEVO v2/C1 — 'con valor/activa' (no afirma default)
  })
  ```

- **[ADICIÓN ARQUITECTO — v2/C1] Lista curada COMPLETA de defaults-ON, confirmada contra
  `config.py`.** Setear `default=True` (editar cada `FlagSpec` agregando `default=True`) en
  las flags que arrancan ON de fábrica. Lista EXACTA (12 keys) = 7 originales (su
  `description` ya declara "default ON") **+ 5 confirmadas por evidencia en
  `backend/config.py`** (arrancan truthy vía `getenv(...,"true")`/`_env_bool(...,True)`):
  - Originales (description dice default ON): `STACKY_EPIC_SANITIZE_ENABLED`,
    `STACKY_EPIC_STRUCTURE_WARNINGS_ENABLED`, `STACKY_COMMENT_FULL_SCAN_ENABLED`,
    `STACKY_ADO_PREVIEW_ENABLED`, `STACKY_GROUNDING_OBSERVATORY_ENABLED`,
    `STACKY_PROCESS_CATALOG_SUGGESTIONS_ENABLED`, `STACKY_OPERATIONAL_HEALTH_ENABLED`.
  - Confirmadas contra `config.py` (v2): `STACKY_EPIC_FROM_BRIEF_ENABLED`,
    `STACKY_EXECUTION_TRACE_ENABLED`, `STACKY_ORPHAN_REAPER_ENABLED`,
    `STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED`, `STACKY_RUNNER_REAP_ON_CLOSE_ENABLED`.

  El resto NO lleva `default=` (cae a type-zero = off/seguro), que ES su default real
  (la inmensa mayoría de `STACKY_*_ENABLED` default OFF).
  > **Procedimiento determinista de verificación (no es vaguedad):** antes de cerrar F0,
  > correr (desde `.../backend`):
  > `& "...python.exe" -c "import re,io;s=open('config.py',encoding='utf-8').read();print([k for k in re.findall(r'([A-Z][A-Z0-9_]+)\\s*[:=].*?(?:getenv|_env_bool|environ\\.get)\\([^)]*?,\\s*(?:True|\"true\"|\"1\"|\"on\")', s)])"`
  > Toda key del registry que aparezca en esa salida y NO esté en la lista de 12 → agregarla
  > (con `default=True`). No inventar: la fuente es `config.py`.
  > **Nota de alcance honesto (v2/C1):** `default` sigue siendo un **hint**; para no mentir,
  > la UI muestra el badge `def:` **solo** cuando `default_known` es True (= esta lista
  > curada), y el resaltado per-flag usa `active` ("con valor", siempre cierto) en lugar de
  > "fuera de default". Introspección autoritativa pre-env de `Config` queda fuera de scope
  > (Config resuelve `os.getenv` en import time, así que el atributo de clase ya no expone el
  > default de fábrica de forma confiable).

**Tests PRIMERO** — archivo: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/tests/test_harness_flags.py`
(AGREGAR funciones; no borrar las existentes):
- `test_every_registry_flag_is_categorized` — `set(s.key for s in FLAG_REGISTRY) == set(_KEY_CATEGORY)`
  (cobertura total y sin keys huérfanas/stale).
- `test_category_keys_no_duplicates_across_categories` — ninguna key aparece en 2 categorías
  (suma de longitudes == tamaño del set unión).
- `test_categorize_known_and_fallback` — `categorize("STACKY_TASK_GATE_ENABLED") == "flujo_funcional"`
  y `categorize("CLAVE_INEXISTENTE_XYZ") == "otros"`.
- `test_list_categories_ids_unique_and_include_otros` — ids únicos, incluye `"otros"`, y
  cada categoría usada en `_CATEGORY_KEYS` existe en `FLAG_CATEGORIES`.
- `test_read_current_includes_category_and_default` — cada dict de `read_current()` tiene
  las claves `"category"`, `"default"`, `"default_known"` y `"active"`; y `"category"` ∈
  ids de `FLAG_CATEGORIES`.
- `test_declared_default_true_set` — definir `CURATED = {las 12 keys de la lista v2}`; para
  cada una `declared_default(spec) is True` **y** `default_is_known(spec) is True`.
- `test_default_known_only_for_curated` (v2/C1) — `{s.key for s in FLAG_REGISTRY if
  default_is_known(s)} == CURATED` (exactamente esas 12; ni más ni menos → bloquea drift).
- `test_declared_default_falls_back_to_type_zero` — para una bool sin `default` (ej.
  `STACKY_TASK_GATE_ENABLED`) `declared_default(spec) is False` y `default_is_known(spec)
  is False`; para un int sin `default` (ej. `STACKY_RUNAWAY_MAX_TURNS`) `== 0`.
- `test_is_active_semantics` (v2/C1+C4) — `is_active(bool_spec, True) is True`;
  `is_active(bool_spec, False) is False`; `is_active(int_spec, 0) is False` y
  `is_active(int_spec, 2) is True`; `is_active(float_spec, 0.0) is False` y
  `is_active(float_spec, 1.0) is True`; `is_active(csv_spec, "") is False` y
  `is_active(csv_spec, "proj-a") is True`. (Construir specs sintéticos por tipo.)
- `test_flagspec_backward_compatible` — `FlagSpec("K","bool","L","D","global").default is None`
  (los campos nuevos son opcionales; construcción legacy no rompe).

**Comando exacto:**
`& "...backend/.venv/Scripts/python.exe" -m pytest tests/test_harness_flags.py -q` (desde `.../backend`).

**Criterio de aceptación BINARIO:** los 10 tests nuevos (v2: +`test_default_known_only_for_curated`,
+`test_is_active_semantics`) + los existentes de `test_harness_flags.py` pasan (exit 0).

**Flag que la protege:** ninguna (mejora aditiva de serialización; no cambia comportamiento).
**Impacto por runtime:** ninguno (no toca el pipeline de ejecución). **Trabajo del operador: ninguno.**

---

### F1 — Backend: exponer las categorías en el endpoint GET

**Objetivo (1 frase).** Que `GET /api/harness-flags` devuelva el orden y los labels de las
categorías, para que el frontend renderice secciones estables y con nombres humanos sin
hardcodear nada. **Valor:** fuente única de verdad de la taxonomía vive en el backend; un
flag/categoría nuevo aparece sin tocar el frontend.

**Archivo a editar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/api/harness_flags.py`

**Símbolo exacto:** `get_harness_flags` (línea 71). Agregar `categories` al JSON:
```python
@bp.get("/harness-flags")
def get_harness_flags():
    from services.harness_flags import read_current, list_categories   # + list_categories
    from services.harness_profiles import detect_profile
    flags = read_current()
    return jsonify({
        "ok": True,
        "flags": flags,
        "active_profile": detect_profile(),
        "categories": list_categories(),   # NUEVO — lista ordenada {id,label,description}
    })
```
(No se toca `put_harness_flags` ni `post_harness_profile`.)

**Tests PRIMERO** — agregar a `test_harness_flags.py`:
- `test_get_harness_flags_includes_categories` — `client.get("/api/harness-flags")` → 200,
  `json["categories"]` es lista no vacía; cada item tiene `id`, `label`, `description`;
  el primer item es `{"id": "runtimes_cli", ...}` (orden estable).
- `test_get_harness_flags_flags_have_category` — cada item de `json["flags"]` tiene
  `category`, `default`, `default_known` y `active`.

**Comando exacto:** igual que F0 (mismo archivo de test).

**Criterio BINARIO:** ambos tests pasan; el JSON existente conserva `ok`, `flags`,
`active_profile` (no se rompe ningún consumidor).

**Flag:** ninguna. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

### F2 — Frontend: contrato de tipos (endpoints.ts)

**Objetivo (1 frase).** Reflejar los campos nuevos del backend en los tipos TS.
**Valor:** type-safety; sin esto el frontend no compila contra los datos nuevos.

**Archivo a editar:** `N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/api/endpoints.ts`

**Símbolos exactos:**
- Extender `HarnessFlagView` (línea 643) con 2 campos:
  ```ts
  export interface HarnessFlagView {
    key: string;
    type: "bool" | "csv" | "int" | "float" | "json" | string;
    label: string;
    description: string;
    group: string;
    pair: string | null;
    env_only: boolean;
    value: boolean | number | string;
    category: string;                          // NUEVO
    default: boolean | number | string;        // NUEVO
    default_known: boolean;                     // NUEVO v2/C1 — render badge def: solo si true
    active: boolean;                            // NUEVO v2/C1 — 'con valor / activa'
  }
  ```
- Agregar interface nueva (junto a `HarnessFlagView`):
  ```ts
  export interface HarnessFlagCategory {
    id: string;
    label: string;
    description: string;
  }
  ```
- Extender el tipo de retorno de `HarnessFlags.list` (línea 822):
  ```ts
  list: () => api.get<{
    ok: boolean;
    flags: HarnessFlagView[];
    active_profile: string | null;
    categories: HarnessFlagCategory[];          // NUEVO
  }>("/api/harness-flags"),
  ```

**Tests PRIMERO:** sin test propio (cambio de tipos). Lo cubren F3/F4 + el gate de `tsc`.

**Comando / criterio BINARIO:**
`npx tsc --noEmit` (desde `.../frontend`) → 0 errores.

**Flag:** ninguna. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

### F3 — Frontend: rediseño del panel en secciones colapsables con ayuda inline

**Objetivo (1 frase).** Reemplazar el render plano por **secciones por categoría**
(colapsables, con descripción de categoría, contador "N flags / M activas"), y mostrar la
**descripción de cada flag inline** + **badge de default** + **resaltado de "modificado"**.
**Valor:** este es el corazón de la claridad.

**Archivos a editar:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/HarnessFlagsPanel.tsx`
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css` (F5)

**Cambios exactos en `HarnessFlagsPanel.tsx`:**
1. Borrar `GROUP_LABELS` (líneas 16-20) y la lógica `groups` por `flag.group`
   (líneas 211-227). El agrupado pasa a ser por `flag.category` usando el orden de
   `data.categories`.
2. Leer `categories` del query: `const categories = data?.categories ?? [];`
3. Construir secciones ordenadas:
   ```ts
   // Mapa categoryId -> flags (excluyendo los que se renderizan como "pair" de un bool)
   const flagsByCat = useMemo(() => {
     const m = new Map<string, HarnessFlagView[]>();
     for (const f of flags) {
       if (flags.some((o) => o.pair === f.key)) continue; // el pair lo dibuja su bool master
       const cat = f.category || "otros";
       if (!m.has(cat)) m.set(cat, []);
       m.get(cat)!.push(f);
     }
     return m;
   }, [flags]);

   // Orden = orden del backend; cualquier categoría no listada va al final.
   const orderedSections = useMemo(() => {
     const known = categories.map((c) => c.id);
     const extra = [...flagsByCat.keys()].filter((id) => !known.includes(id));
     return [...categories, ...extra.map((id) => ({ id, label: id, description: "" }))]
       .filter((c) => (flagsByCat.get(c.id)?.length ?? 0) > 0);
   }, [categories, flagsByCat]);
   ```
4. **[ADICIÓN ARQUITECTO — v2/C1] Señal honesta.** NO inventar un helper `isModified`
   (afirmaría conocer el default real, que NO conocemos para la mayoría). Usar los campos
   que ya manda el backend:
   - `f.active` → "con valor / activa" (siempre cierto; no afirma default).
   - `f.default_known` → si renderizar o no el badge `def:`.
   ```ts
   // 'activa/con valor' = el backend ya lo computó (is_active). Sin claim de default.
   const isActive = (f: HarnessFlagView): boolean => f.active;
   ```
5. Render de cada sección con `<details>` (colapsable nativo, accesible, sin librerías):
   - `<summary>`: label de categoría + descripción + contador. **v2/C3 — métricas
     separadas, sin mezclar:** `"{activeBools}/{totalBools} activas · {nonBoolWithValue} con valor"`
     donde `activeBools` = bools (`type==="bool"`) con `value===true`; `totalBools` = bools
     de la sección; `nonBoolWithValue` = no-bools con `f.active===true`. (Si la sección no
     tiene bools, omitir el "N/M activas".)
   - **`open` por defecto** = la sección tiene ≥1 flag con `f.active` (algo encendido o con
     valor). Surfacea lo que está en uso y deja el resto plegado.
   - **IMPORTANTE (no romper tests):** las filas SIEMPRE se montan en el DOM, aunque la
     sección esté colapsada (`<details>` cerrado mantiene los hijos en el DOM; jsdom no
     desmonta hijos de `<details>`, por eso `getByText` los encuentra). NO desmontar el
     contenido al colapsar.
6. `FlagRow` (localizar por símbolo `FlagRow`/`control()`, confirmar con grep — los rangos
   de línea son orientativos): conservar `control()`, el toggle, los inputs y el render del
   `pair` CSV. **Cambios:**
   - Mostrar la **descripción inline** SIEMPRE (no solo en `title`): nuevo elemento
     `<p className={styles.flagDesc}>{flag.description}</p>` debajo del nombre. (Reusa
     `flag.description` del registry; no se inventa texto.)
   - Mantener el `?` con `title` como ayuda secundaria (opcional).
   - **Badge de default SOLO si `flag.default_known`** (v2/C1):
     `{flag.default_known && <span className={styles.defaultBadge}>def: {fmtDefault(flag)}</span>}`
     donde `fmtDefault` mapea bool→"ON"/"OFF", y otros→`String(flag.default) || "vacío"`.
     Si `default_known` es false, NO renderizar badge (no mentir un default).
   - Si `isActive(flag)`, agregar `className` extra `styles.activeRow` (resalte sutil de
     "en uso/con valor"). NO usar la etiqueta "modificado/fuera de default".
7. Conservar la barra de perfil (`profileBar`, líneas 238-255) tal cual.

**Tests PRIMERO** — archivo: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/__tests__/HarnessFlagsPanel.test.tsx`
(extender fixtures y reescribir las aserciones que dependían de los labels de grupo):
- Actualizar `MOCK_RESPONSE` para incluir `category`, `default`, `default_known` y `active`
  en cada fixture, y agregar `categories: [{id:"runtimes_cli",label:"Runtimes CLI (Claude /
  Codex)",description:"..."}, {id:"contexto_memoria",label:"Contexto y memoria",description:"..."},
  ...]` cubriendo las categorías usadas por los fixtures.
- Reescribir `renderiza grupos y labels...` → `test "renderiza secciones por categoría con labels del backend"`:
  `screen.getByText("Runtimes CLI (Claude / Codex)")` visible (ya no "Global"/"Claude Code CLI").
- NUEVO `cada flag muestra su descripción inline`: `screen.getByText("F1.1 — Si ON, outputs con errores duros degradan el run a needs_review.")` (texto exacto del fixture) está en el DOM.
- NUEVO (v2/C1) `badge def: solo cuando default_known`: una flag con `default_known:true,
  default:true` muestra el badge "def: ON"; una flag con `default_known:false` NO renderiza
  badge (verificar `screen.queryByText(/^def:/)` ausente para esa fila / presente para la otra).
- NUEVO (v2/C1) `resalta flags activas con activeRow`: una flag con `active:true` tiene la
  clase `activeRow` (`container.querySelector(".activeRow")` o `toHaveClass`); una con
  `active:false` no.
- NUEVO `sección colapsable expande/colapsa al click`: click en el `<summary>` cambia
  `open`. (Como el contenido queda montado, además verificar que el `<details>` con ≥1 flag
  `active:true` arranca `open`.)
- **MANTENER VERDES** (ajustando solo lo mínimo): toggle bool llama update; JSON inválido
  no llama update; botón perfil "safe"; error de API inline.

**Comando / criterio BINARIO (v2/C2):**
- **Gate binario vinculante:** `npx tsc --noEmit` (desde `.../frontend`) → 0 errores. Este
  es el ÚNICO criterio de aceptación que decide la fase.
- **No vinculante (toolchain ausente):** `npx vitest run src/components/__tests__/HarnessFlagsPanel.test.tsx`.
  vitest NO está instalado en este entorno (memoria `backend-dev-test-env`); el `.test.tsx`
  se escribe completo según convención y se corre cuando el toolchain esté disponible. Su
  ausencia NO bloquea la fase.

**Flag:** ninguna. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

### F4 — Frontend: búsqueda/filtrado + resumen global + filtro "solo modificados"

**Objetivo (1 frase).** Agregar una caja de búsqueda (filtra por label/descripción/key),
un toggle "solo modificados", y un encabezado de resumen (total flags / activas).
**Valor:** elimina la sensación de lista interminable; el operador llega a lo que busca.

**Archivo a editar:** `HarnessFlagsPanel.tsx` (mismo de F3).

**Cambios exactos:**
1. Estado local: `const [q, setQ] = useState(""); const [onlyActive, setOnlyActive] = useState(false);`
   (v2/C1: el filtro se llama "solo activas / con valor", no "modificados").
2. Caja de búsqueda accesible arriba de las secciones:
   `<input type="search" aria-label="Buscar flag" placeholder="Buscar por nombre, descripción o clave..." value={q} onChange={...} className={styles.search}/>`
   y un checkbox `aria-label="Solo activas"` (label visible "Solo activas / con valor").
3. Predicado de filtro (case-insensitive; sin dependencias nuevas):
   ```ts
   function matches(f: HarnessFlagView): boolean {
     if (onlyActive && !f.active) return false;       // v2/C1 — usa active, no un default inferido
     if (!q.trim()) return true;
     const n = q.trim().toLowerCase();
     return f.label.toLowerCase().includes(n)
         || f.description.toLowerCase().includes(n)
         || f.key.toLowerCase().includes(n);
   }
   ```
   Aplicar `matches` al construir `flagsByCat` (F3). Secciones que quedan vacías tras el
   filtro NO se renderizan (`orderedSections` ya filtra por length > 0).
4. **Auto-expand bajo búsqueda/filtro:** si `q.trim() !== "" || onlyActive`, forzar
   `open` en todas las secciones visibles (pasar un prop `forceOpen` al `<details>`:
   `<details open={forceOpen || sectionHasActive}>`) donde `sectionHasActive` = la sección
   tiene ≥1 flag con `f.active`.
5. Encabezado de resumen arriba (debajo de la profileBar) — **v2/C3 métricas separadas**:
   `<div className={styles.summary}>{total} flags · {activeCount} activas/con valor · {knownDefaults} con default conocido</div>`.
   (`total` = todas las flags menos las que son pair; `activeCount` = `f.active===true`;
   `knownDefaults` = `f.default_known===true`. NO se reporta "fuera de default" porque no
   conocemos el default real de la mayoría.)

**Tests PRIMERO** — agregar a `HarnessFlagsPanel.test.tsx`:
- `filtra por texto y oculta lo que no coincide`: escribir en la búsqueda un término que
  matchea 1 flag → `screen.getByText(<label match>)` visible y `screen.queryByText(<label no-match>)` null.
- `filtro 'solo activas' muestra solo flags con valor` (v2/C1): activar el checkbox →
  solo las filas con `active:true` quedan en el DOM (las `active:false` salen).
- `muestra el resumen con conteos`: `screen.getByText(/flags/)` contiene el total esperado
  del mock.

**Comando / criterio BINARIO:** `npx vitest run ...HarnessFlagsPanel.test.tsx` verde +
`npx tsc --noEmit` 0 errores.

**Flag:** ninguna. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

### F5 — Frontend: CSS + accesibilidad (polish) + regresión del sub-tab

**Objetivo (1 frase).** Estilar las secciones/accordion/badges/búsqueda y asegurar
accesibilidad, sin romper el sub-tab "Arnes" de SettingsPage. **Valor:** jerarquía visual
real y experiencia pulida.

**Archivos a editar:**
- `N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/components/HarnessFlagsPanel.module.css`

**Clases nuevas exactas a agregar** (conservar las existentes que usan otros nodos):
`.search`, `.summary`, `.section` (estilo del `<details>`), `.sectionSummary`
(estilo del `<summary>`: cursor pointer, header con flecha), `.sectionMeta` (descripción
+ contador en gris pequeño), `.flagDesc` (texto secundario, line-height holgado,
`white-space: normal` — a diferencia de `.flagName` que tiene `nowrap`), `.defaultBadge`
(pill chico gris), `.activeRow` (v2/C1 — borde/realce sutil de "en uso/con valor", ej.
`border-left: 3px solid var(--color-primary)`).
- Accesibilidad: el `<summary>` es focuseable por defecto; agregar `aria-label` a la
  búsqueda y al checkbox; los toggles ya usan `<input type="checkbox">`.

**Regresión del sub-tab** — archivo: `N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend/src/pages/__tests__/SettingsPage.harness.test.tsx`:
- Su mock (`list`) devuelve 1 flag y `active_profile:null`. **Agregar** al mock los campos
  `category:"runtimes_cli"`, `default:false`, `default_known:false`, `active:false` en el
  flag, y `categories:[{id:"runtimes_cli", label:"Runtimes CLI (Claude / Codex)",
  description:""}]` en la respuesta.
- Las 2 aserciones existentes (`getByText("Gate de contrato (claude)")` visible / oculto al
  cambiar de tab) **siguen verdes** porque las filas se montan aunque la sección esté
  colapsada (ver F3 punto 5). No cambiar la lógica del test salvo el mock.

**Comando / criterio BINARIO:**
- `npx tsc --noEmit` (desde `.../frontend`) → 0 errores **(gate que corre)**.
- `npx vitest run src/pages/__tests__/SettingsPage.harness.test.tsx src/components/__tests__/HarnessFlagsPanel.test.tsx`
  → verde (cuando el toolchain esté disponible).
- Revisión visual: levantar el frontend y confirmar secciones colapsables, descripción
  inline, badges de default, búsqueda y resumen (manual; no bloqueante de CI).

**Flag:** ninguna. **Runtime:** sin impacto. **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Lista `_CATEGORY_KEYS` incompleta o con typo (key inexistente) | Test bidireccional `test_every_registry_flag_is_categorized` + regla de recuperación determinista. Falla en CI antes de mergear. |
| Romper consumidores del endpoint al cambiar el JSON | Solo se AGREGAN campos (`category`, `default`, `categories`); los existentes quedan intactos. Tests `test_get_harness_flags_*` lo verifican. |
| Tests de frontend que asertaban labels de grupo ("Global") | F3 los reescribe explícitamente a labels de categoría; el resto se mantiene con cambios mínimos de fixture. |
| Sección colapsada esconde la flag a `getByText` en tests | F3/F5 mandan montar siempre las filas (`<details>` no desmonta hijos). SettingsPage test verde. |
| `default` declarado no coincide con el default real de `config.py` (mentía en ≥5 flags default-ON) | **v2/C1 resuelto:** lista curada completada contra `config.py` (12 keys); el badge `def:` se muestra SOLO si `default_known`; el resaltado per-flag usa `active` ("con valor", siempre cierto), no un default inferido. Test `test_default_known_only_for_curated` bloquea drift. |
| El criterio binario exige vitest, que no está instalado | **v2/C2 resuelto:** gate binario vinculante = `npx tsc --noEmit` 0 errores; `.test.tsx` escritos pero no bloqueantes hasta tener toolchain. |
| Un plan futuro agrega una flag y el ratchet rompe CI sin contexto | **v2/C6:** comentario en cabecera de `FLAG_REGISTRY` apunta a `_CATEGORY_KEYS`; la regla de recuperación determinista explica cómo categorizar. |
| Romper las 142 construcciones de `FlagSpec` al tocar la dataclass | El campo `default` se agrega **al final** y con valor por defecto `None`; construcción legacy intacta (test `test_flagspec_backward_compatible`). |
| vitest no instalado en el entorno | Gate real = `tsc --noEmit`; los `.test.tsx` quedan escritos por convención y corren cuando el toolchain esté (igual que el resto del repo). |

## 6. Fuera de scope

- Introspección autoritativa de los defaults reales de `config.py` (snapshot pre-env).
- Editar/agregar/quitar flags del arnés o cambiar su semántica.
- Tocar el pipeline de ejecución de cualquier runtime.
- Persistir el estado de colapso/búsqueda entre sesiones (es estado efímero de UI).
- Reordenar flags dentro de una categoría por relevancia/uso (posible plan futuro).
- Internacionalización (la UI es español, mono-operador).

## 7. Glosario + Orden de implementación + DoD

**Glosario (términos Stacky para un modelo menor):**
- **Arnés (harness):** capa de flags que modula cómo Stacky corre los agentes (gates,
  verificación, memoria, routing). Se edita 100% por UI.
- **FLAG_REGISTRY:** tupla declarativa en `services/harness_flags.py` que describe cada
  flag (key, tipo, label, descripción, grupo, pair, env_only). Fuente única.
- **env_only:** la flag vive solo en `os.environ` (no es atributo de `Config`); se lee en
  call time. No cambiar esto en este plan.
- **pair:** flag CSV de allowlist de proyectos asociada a un bool (la UI los dibuja juntos).
- **group vs category:** `group` es el campo técnico actual (3 conocidos + varios crudos);
  `category` (este plan) es la taxonomía humana de ~13 secciones para la UI. `group` NO se
  toca (lo usan tests existentes); `category` se deriva aparte.
- **declared_default / default_known:** `declared_default` es el valor "de fábrica" hint;
  `default_known` (v2) es True solo en las 12 flags curadas+confirmadas contra `config.py`,
  y la UI muestra el badge `def:` SOLO cuando es True (no afirma defaults no confirmados).
- **active ("con valor / activa"):** una flag cuyo `value` difiere de su type-zero (bool en
  true, número ≠ 0, csv/json no vacío). Claim siempre cierto, no depende del default real.
  Reemplaza al concepto "modificado/fuera de default" de v1.
- **3 runtimes:** Codex CLI, Claude Code CLI, GitHub Copilot Pro.

**Orden de implementación:**
1. F0 (backend: dataclass + categorías + helpers + read_current + tests) → verde.
2. F1 (backend: endpoint expone categories + tests) → verde.
3. F2 (frontend: tipos endpoints.ts) → `tsc` verde.
4. F3 (frontend: secciones colapsables + ayuda inline + default + tests) → tsc verde.
5. F4 (frontend: búsqueda/filtro + resumen + tests) → tsc verde.
6. F5 (frontend: CSS/a11y + regresión SettingsPage) → tsc verde + (vitest cuando aplique).

**Definición de Hecho (DoD) global:**
- [ ] `test_harness_flags.py` pasa completo con los ≥12 tests nuevos (F0+F1; v2 suma
      `test_default_known_only_for_curated` y `test_is_active_semantics`).
- [ ] El JSON de `GET /api/harness-flags` conserva `ok/flags/active_profile` y agrega
      `categories`, y cada flag agrega `category` + `default` + `default_known` + `active`.
- [ ] `npx tsc --noEmit` en frontend = 0 errores **(gate binario vinculante; vitest no
      bloquea por estar ausente en el entorno — v2/C2)**.
- [ ] `HarnessFlagsPanel` renderiza secciones colapsables por categoría con descripción
      inline, badge `def:` SOLO en flags con `default_known`, resaltado de flags `active`,
      búsqueda y resumen con métricas separadas (activas / con default conocido).
- [ ] `SettingsPage.harness.test.tsx` sigue verde (mock actualizado).
- [ ] Ninguna flag nueva; ningún cambio de comportamiento del arnés; cero trabajo extra
      al operador; sin impacto en runtimes.
- [ ] Todas las flags siguen siendo editables por UI (regla dura respetada).
