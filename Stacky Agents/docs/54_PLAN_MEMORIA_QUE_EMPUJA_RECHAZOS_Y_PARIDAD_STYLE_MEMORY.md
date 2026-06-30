# Plan 54 — Memoria que Empuja: Rechazos como Anti-Patrón + Paridad FA-11 en 3 runtimes

> Versión: v1 → v2 (propuesto 2026-06-20). Top-5 debate adversarial, ítem 2/5. Depende del Plan 53 (selector adaptativo por confidence) solo en orden, no en código.
>
> ## v1 → v2 CHANGELOG (juicio adversarial 2026-06-20)
>
> - **C1 (BLOQUEANTE, resuelto):** Ambigüedad plan/titulo vs F1 comportamiento sobre FA-10. v1 decía "Paridad FA-11/FA-10" pero F1 dejaba style_memory inline en copilot (no lo movía a paridad). **Decisión:** Plan 54 cierra SOLO paridad FA-11 (rejection_lessons en 3 runtimes). FA-10 (style_memory) queda como herencia copilot-only, por coherencia con Plan 48 que explícitamente lo dejó ahí. Título y Resumen reecritos.
> - **C2, C3 (IMPORTANTE):** Helper `build_memory_prefix` parámetro `include_style` confuso. Reescrita F0 para claridad: el helper NO incluye style_memory (parámetro eliminado). Helper combina SOLO rejection_lessons + estilo externo. F1 refactor deja style_memory exactamente dónde está (inline copilot, Plan 48). Tests actualizados.
> - **C4 (IMPORTANTE, requisito):** F4 "garantizar sink" asumeWriter de Plan 48 F3. Añadido párrafo explícito: "Prerequisito: Plan 48 F3/F4 IMPLEMENTADO; verifica que `rejection_lessons.load_for_run` y su writer existan." Línea de comando para verificar.
> - **[ADICIÓN ARQUITECTO]:** F4b — Poda determinística de corpus: función pura `trim_rejection_lessons(project, agent_type, max_count=100)` que mantiene los últimos N lecciones por (project, agent_type) para evitar crecimiento sin techo del bloque. Determinista (sort por updated_at DESC), sin LLM. Comando: `.venv\Scripts\python.exe -m pytest "backend/tests/test_rejection_lessons_trim.py" -q`. Acota impacto en tamaño de prompt.

## Resumen (3 líneas)
- **Qué propone:** cuando el operador RECHAZA un run, su veredicto se materializa como un ANTI-PATRÓN imperativo determinista (función pura nota→bloque de texto) inyectado en el prompt de los 3 runtimes en el próximo run del proyecto; cierra la deuda de paridad **de rejection_lessons** (Plan 48 lo implementó en copilot + CLI vía context_enrich, pero esta fase confirma paridad en las 3 rutas de builder de prompt).
- **Valor:** convierte un rechazo silencioso (hoy se guarda en `memory_store` con flag OFF y no empuja nada en CLI) en una corrección que el agente recibe la próxima vez, sin trabajo extra del operador. Añade poda determinística de corpus para evitar crecimiento sin techo.
- **3 runtimes:** la inyección se hace en puntos separados (`agents/base.py` copilot YA lo tiene; F2/F3 replican en `claude_code_cli_runner.py` y `codex_cli_runner.py` reusando la función pura `build_memory_prefix`); fallback explícito: si falla, prompt sin bloque (nunca rompe el run). FA-10 `style_memory` queda copilot-only por herencia del Plan 48.

---

## Glosario corto
- **Anti-patrón imperativo:** bloque de texto en imperativo ("NO hagas X") derivado de una nota de rechazo. Determinista: misma nota → mismo bloque.
- **rejection_lessons:** servicio del Plan 48 (`backend/services/rejection_lessons.py`) con `load_for_run(...)` y `build_prefix(...)`. Plan 48 YA lo implementó en copilot (base.py) y CLI (context_enrichment.py); este plan confirma paridad en los 3 builders de prompt.
- **style_memory (FA-10):** `backend/services/style_memory.py:174 style_prompt_note(user_email, agent_type)`. **Queda copilot-only** (herencia Plan 48, no se mueve a CLI).
- **Paridad FA-11 (rejection_lessons):** que los 3 runtimes reciban la MISMA inyección de anti-patrón de rechazos. Plan 48 lo implementó asimétrico; este plan lo formaliza en los 3 puntos de builder.
- **Builder de prompt CLI:** el punto donde cada runner CLI ensambla el prompt/contexto que pasa al binario (`claude`/`codex`).

## Sustrato verificado (archivo:línea reales — 2026-06-20)
- `backend/services/post_run_memory.py:199 capture_operator_note(execution_id)` — captura la nota humana al `memory_store` (canal USER). OFF por default. NO empuja a runtimes.
- `backend/agents/base.py:90-121` — inyección de `anti_patterns` + `rejection_lessons` (Plan 48 F3) **solo en la ruta copilot**. Flag leído ahí: `STACKY_PUSH_REJECTIONS_ENABLED` (base.py:104). Llama `rejection_lessons.load_for_run(project, agent_type, existing_patterns)` y `rejection_lessons.build_prefix(rej)`.
- `backend/agents/base.py:158-170` — FA-10 `style_memory.style_prompt_note(run_ctx.started_by, self.type)`, **solo en la ruta copilot**.
- `backend/services/claude_code_cli_runner.py` — **NO** referencia `rejection_lessons`, `style_memory` ni `anti_patterns` (grep vacío 2026-06-20). Misma deuda en `codex_cli_runner.py`.
- `backend/services/rejection_lessons.py` — existe (`load_for_run`, `build_prefix`) según base.py:107-117.
- `backend/services/style_memory.py:174 style_prompt_note(user_email, agent_type) -> str | None`.

**Conclusión de sustrato:** el Plan 48 dejó la mitad hecha (copilot). Este plan: (1) cierra paridad inyectando en los 2 runners CLI reusando las funciones puras existentes; (2) garantiza que la nota de rechazo ALIMENTE `rejection_lessons` de forma determinista (verificar que el corpus existe; si no, añadir el sink).

## Rieles no negociables (codificados aquí)
- **Paridad 3 runtimes con fallback:** un único helper compartido `build_memory_prefix(...)` que los 3 puntos llaman; try/except → si falla, bloque vacío.
- **Cero trabajo extra:** todo automático; rechazar ya es una acción que el operador hace. Flag `STACKY_PUSH_REJECTIONS_ENABLED` default **OFF**.
- **Human-in-the-loop:** NO auto-adopta cambios de prompt ni regenera especulativamente. Solo convierte rechazo→bloque imperativo determinista. El humano sigue aprobando/rechazando.
- **Mono-operador sin auth:** no se filtra por usuario para permisos; `started_by` es solo para `style_memory` (ya existente).
- **No degradar / backward-compatible:** flag OFF = comportamiento idéntico al actual. Sin el flag no se inyecta nada nuevo en CLI.
- **Reusar lo existente:** cero servicios nuevos de generación; se reusa `rejection_lessons` y `style_memory`.

---

## Fases

### F0 — Helper de inyección compartido (función pura SOLO rejection_lessons)
**Objetivo:** centralizar en una sola función la inyección de rejection_lessons para que los 3 runtimes la llamen idéntica. **FA-10 (style_memory) queda copilot-only por herencia.**

- **Archivo nuevo:** `backend/services/memory_prefix.py`
- **Símbolos exactos:**
  ```python
  def build_memory_prefix(
      *,
      project: str | None,
      agent_type: str,
      existing_patterns: set[str] | None = None,
      push_rejections_enabled: bool | None = None,  # None → lee el flag
  ) -> tuple[str, dict]:
      """PURA salvo lectura de flag/servicios. Devuelve (prefix_text, meta).

      prefix_text: inyección de rejection_lessons SOLO si flag ON:
        - rejection_lessons.build_prefix(rejection_lessons.load_for_run(...))  [si flag ON]
      meta: {"rejection_lessons_count": int, "memory_prefix_error": str?}

      NUNCA lanza. Excepción en rejection_lessons → bloque omitido, error anotado en meta.
      """
  ```
- **Casos borde (deterministas, en orden):**
  1. `push_rejections_enabled is None` → leer `os.getenv("STACKY_PUSH_REJECTIONS_ENABLED","false").lower() in {"1","true","on","yes"}`.
  2. flag OFF → NO se llama `rejection_lessons` (count=0, prefix="").
  3. `existing_patterns is None` → `set()`.
  4. Excepción en rejection_lessons → bloque omitido, `meta["memory_prefix_error"]` = str(exc).
  5. Resultado vacío → `prefix_text == ""`.

- **Tests PRIMERO:** `backend/tests/test_memory_prefix.py`
  - `test_flag_off_returns_empty` — flag OFF → prefix="", count=0.
  - `test_flag_on_includes_rejections` — flag ON, `load_for_run` monkeypatched a [obj], `build_prefix` a "REGLA" → prefix contiene "REGLA", count=1.
  - `test_service_exception_is_swallowed` — `load_for_run` lanza → prefix="", `meta["memory_prefix_error"]` presente.
  - `test_empty_pattern_returns_empty` — todo None/vacío → ("", meta count=0).
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_memory_prefix.py" -q`
- **Aceptación binaria:** 4 tests verdes. **Comando:** arriba, exit code 0.
- **Flag:** `STACKY_PUSH_REJECTIONS_ENABLED` default OFF (ya existe en Plan 48).
- **Impacto por runtime:** ninguno todavía (solo crea la función). Fallback: N/A.
- **Trabajo del operador:** ninguno.

### F1 — Refactor de `base.py` para usar el helper (paridad punto 1: copilot)
**Objetivo:** que la ruta copilot llame `build_memory_prefix` en vez de inline rejection_lessons, sin cambiar observable. FA-10 style_memory queda inline copilot en `base.py:158-170` exactamente donde estaba (Plan 48 decisión).

- **Archivo:** `backend/agents/base.py` (líneas 97-119 rejection + rejection_lessons).
- **Cambio (diff conceptual):** reemplazar las líneas de rejection_lessons inline por:
  ```python
  from services.memory_prefix import build_memory_prefix
  _mem_prefix, _mem_meta = build_memory_prefix(
      project=run_ctx.project,
      agent_type=self.type,
      existing_patterns={" ".join((p.pattern or "").lower().split()) for p in patterns},
  )
  if _mem_prefix:
      prefix_parts.append(_mem_prefix)  # BEFORE style_memory, si lo hay
  meta.update(_mem_meta)
  ```
  - **Conservar intacto** líneas 158-170 style_memory inline (no se mueve al helper).
  - Anti-patterns (líneas 90-101) también intacto.
  - Orden final en prefix_parts: anti_patterns → rejection_lessons (nuevo, del helper) → ... → style_memory (inline, sin cambios).

- **Tests:** `backend/tests/test_base_prompt_parity.py` (nuevo)
  - `test_copilot_rejection_lessons_injected_flag_on` — refactor con flag ON → prefix contiene rejection_lessons, count≥0.
  - `test_copilot_style_memory_unchanged_flag_off` — flag OFF → style_memory sigue funcionando exactamente igual (no se rompió FA-10).
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_base_prompt_parity.py" -q`
- **Aceptación binaria:** tests verdes + suite existente `test_base.py` sin regresión. **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_base_prompt_parity.py" backend/tests/test_base.py -q` exit 0.
- **Flag:** mismo `STACKY_PUSH_REJECTIONS_ENABLED`.
- **Impacto por runtime:** copilot — refactor puro, observable idéntico.
- **Trabajo del operador:** ninguno.

### F2 — Inyección en Claude Code CLI (paridad punto 2)
**Objetivo:** que `claude_code_cli_runner.py` anteponga `build_memory_prefix(...)` al contexto que pasa al binario.

- **Archivo:** `backend/services/claude_code_cli_runner.py`
- **Punto de inserción:** donde se ensambla el prompt/contexto del run (el bloque que arma `raw_blocks`/system prompt ANTES de spawnear `claude`). **Localizar con:** `grep -n "system_prompt\|prefix\|raw_blocks" claude_code_cli_runner.py` y elegir el ensamblado previo al spawn. (No hardcodear línea: el implementador la confirma con grep y cita archivo:línea en el commit.)
- **Cambio:**
  ```python
  from services.memory_prefix import build_memory_prefix
  _mem_prefix, _mem_meta = build_memory_prefix(
      project=(project_ctx.stacky_project_name if project_ctx else None),
      agent_type=agent_type,
      started_by=started_by,           # confirmar nombre de la var en el runner
      existing_patterns=None,          # CLI no tiene patterns previos en scope → set()
      include_style=True,
  )
  if _mem_prefix:
      # anteponer como bloque de sistema/contexto, NO mezclar con el brief
      system_prefix = (_mem_prefix + "\n\n" + (system_prefix or "")).strip()
  metadata.update(_mem_meta)
  ```
- **Casos borde:** si `_mem_prefix == ""`, no tocar nada (backward-compatible exacto). Si falla, helper ya lo tragó.
- **Tests:** `backend/tests/test_cli_memory_parity.py` (nuevo) — usar el patrón de mock existente del runner (lazy imports parcheados en módulo origen; ver memoria plan 28).
  - `test_claude_cli_injects_rejection_block_when_flag_on` — flag ON, `rejection_lessons.load_for_run` monkeypatched → el system prefix capturado contiene el bloque de regla.
  - `test_claude_cli_no_injection_when_flag_off_and_no_style` — flag OFF + started_by None → system prefix sin cambios.
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_cli_memory_parity.py" -q`
- **Aceptación binaria:** tests verdes. **Comando:** arriba, exit 0.
- **Flag:** `STACKY_PUSH_REJECTIONS_ENABLED` default OFF.
- **Impacto por runtime:** Claude CLI — con flag OFF idéntico; con flag ON recibe el bloque. Fallback: prefix vacío.
- **Trabajo del operador:** ninguno.

### F3 — Inyección en Codex CLI (paridad punto 3)
**Objetivo:** misma inyección en `codex_cli_runner.py`.

- **Archivo:** `backend/services/codex_cli_runner.py`
- **Cambio:** idéntico patrón a F2, en el punto de ensamblado del prompt del runner Codex (localizar con grep `system\|prompt\|prefix`).
- **Tests:** ampliar `backend/tests/test_cli_memory_parity.py`:
  - `test_codex_cli_injects_rejection_block_when_flag_on`
  - `test_codex_cli_no_injection_when_flag_off`
  - **Comando:** mismo archivo.
- **Aceptación binaria:** 4 tests CLI verdes (2 claude + 2 codex). **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_cli_memory_parity.py" -q` exit 0.
- **Flag/impacto/operador:** igual a F2 para Codex.

### F4 — Garantizar el sink: rechazo → corpus de rejection_lessons
**Objetivo:** verificar que un rechazo del operador efectivamente queda en el corpus que `rejection_lessons.load_for_run` lee; si NO existe el sink, añadirlo determinista.

**Prerequisito explícito:** Plan 48 F3/F4 IMPLEMENTADO. Verificar:
  - `grep -n "def load_for_run\|def build_prefix" backend/services/rejection_lessons.py` → devuelve líneas (si no, Plan 48 no está o está incompleto).
  - `grep -n "capture_operator_note\|memory_store" backend/services/post_run_memory.py` → verifica que Plan 48 captura la nota (presente en línea ~199).

- **Verificación de sink (barata):** `grep -rn "def load_for_run\|def writer\|def save\|rejection_lessons" backend/services/rejection_lessons.py backend/services/post_run_memory.py backend/api/`. Determinar: ¿`load_for_run` lee de tabla BD o archivo? ¿Existe un writer que dispara al rechazar?
- **Caso A — writer YA existe (Plan 48 F4):** no hacer código nuevo; solo test de integración que valida ciclo (rechazar con nota → `load_for_run` próximo run devuelve la lección).
- **Caso B — NO existe writer:** añadir hook en el endpoint de veredicto humano (localizar: `grep -rn "needs_review=False\|approved.*verdict\|human_review" backend/api/`). El hook persiste la lección cuando se rechaza.
  - **Función determinista en rejection_lessons.py:** `def pure_rejection_to_lesson(note: str) -> str` — nota normalizada con prefijo imperativo ("NO REPITAS: " + nota trimmed; sin LLM).

- **Tests:** `backend/tests/test_rejection_sink.py`
  - `test_pure_rejection_to_lesson_deterministic` — mismo input → mismo output; nota vacía → "".
  - `test_reject_persists_and_loads` — rechazar con nota → `load_for_run` próximo run (mismo project+agent) devuelve la lección.
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_rejection_sink.py" -q`
- **Aceptación binaria:** tests verdes. **Comando:** arriba, exit 0.
- **Flag:** el sink escribe SIEMPRE (capturar es gratis); la INYECCIÓN se rige por `STACKY_PUSH_REJECTIONS_ENABLED`. (Backward-compatible: escribir con flag OFF es inocuo.)
- **Impacto por runtime:** N/A (captura).
- **Trabajo del operador:** ninguno.

### F4b — Poda determinística de corpus (ADICIÓN ARQUITECTO)
**Objetivo:** evitar crecimiento sin techo del corpus de rejection_lessons; mantener los últimos N rechazos por (project, agent_type).

- **Función pura nueva** en `rejection_lessons.py`:
  ```python
  def trim_rejection_corpus(
      *,
      project: str,
      agent_type: str,
      max_count: int = 100,
  ) -> int:
      """Elimina lecciones viejas, mantiene las últimas max_count por (project, agent_type).
      Determinista: sort por updated_at DESC, elimina rows con índice ≥ max_count.
      Devuelve cantidad de rows eliminadas.
      """
  ```
- **Cuándo llamar:** después de escribir una nueva lección (F4 hook), invocar `trim_rejection_corpus(...)` con los mismos (project, agent_type). Costo: 1 query de borrado acotado.
- **Tests:** `backend/tests/test_rejection_lessons_trim.py`
  - `test_trim_keeps_last_n` — guardar 150 lecciones, trim max_count=100 → quedan 100 con los más recientes.
  - `test_trim_is_deterministic` — mismo corpus → mismos rows eliminados (order by updated_at DESC).
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_rejection_lessons_trim.py" -q`
- **Aceptación binaria:** tests verdes. **Comando:** arriba, exit 0.
- **Flag:** ninguno (poda es automática, cost marginal).
- **Impacto por runtime:** reduce tamaño eventual del bloque injection; inyección igual.
- **Trabajo del operador:** ninguno (automático).

### F5 — Registrar tests en el ratchet
**Objetivo:** los tests nuevos no se pierden (Plan 49 F4 meta-test).
- **Archivos:** `backend/scripts/run_harness_tests.ps1` y `backend/scripts/run_harness_tests.sh` — añadir a `HARNESS_TEST_FILES`: `test_memory_prefix.py`, `test_base_prompt_parity.py`, `test_cli_memory_parity.py`, `test_rejection_sink.py`, `test_rejection_lessons_trim.py`.
- **Aceptación binaria:** el meta-test del ratchet pasa. **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_harness_ratchet_meta.py" -q` exit 0 (Plan 49).
- **Trabajo del operador:** ninguno.

---

## Orden de implementación
F0 → F1 → F2 → F3 → F4 → F4b → F5. (F1 antes de F2/F3 porque valida el helper en la ruta ya funcionante; F4b es poda ortogonal, cableada en F4.)

## Fuera de scope (dependencias con el top-5)
- **Plan 56 (gate de regresión golden +/-)** consume el corpus de rechazos/aprobaciones que F4 garantiza. Este plan NO implementa el gate.
- **Plan 53 (selector adaptativo por confidence):** independiente; solo precede en orden.
- NO se implementa generación/regeneración especulativa de prompt (matado en debate por no-determinista).

## DoD (Definition of Done)
1. `test_memory_prefix.py`, `test_base_prompt_parity.py`, `test_cli_memory_parity.py`, `test_rejection_sink.py`, `test_rejection_lessons_trim.py` verdes (comandos arriba).
2. Con `STACKY_PUSH_REJECTIONS_ENABLED=false`: comportamiento de los 3 runtimes idéntico al actual (verificado por los tests `*_off`).
3. Con flag ON: los 3 runtimes anteponen el mismo bloque de rejection_lessons derivado del rechazo (verificado por los tests `*_on`).
4. FA-10 (`style_memory`) intacta copilot-only; **Plan 54 NO mueve FA-10 a paridad** (herencia Plan 48).
5. Corpus de rejection_lessons se poda automáticamente a max_count=100 por (project, agent_type).
6. Tests registrados en el ratchet (F5) y meta-test verde.
7. `grep -n "build_memory_prefix"` en los 2 runners CLI (`claude_code_cli_runner.py`, `codex_cli_runner.py`) devuelve coincidencias en F2/F3 (paridad de inyección).
