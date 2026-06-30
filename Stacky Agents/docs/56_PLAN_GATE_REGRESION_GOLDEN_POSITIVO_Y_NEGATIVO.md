# Plan 56 — Gate de Regresión: Golden Positivo + Golden Negativo

> Versión: v1 → v2 (propuesto 2026-06-20). Top-5 debate adversarial, ítem 4/5. **Depende del Plan 54** (corpus de rechazos/aprobaciones).
>
> ## v1 → v2 CHANGELOG (juicio adversarial 2026-06-20)
>
> - **C8 (BLOQUEANTE, documentado):** Matching substring es heurística frágil. Reescrita F0 con advertencia: goldens negativos usan substring normalizado (case-insensitive); riesgo = false-negatives si nota varía en redacción. Mitigación: operador ve la regresión como warning (modo default), no bloqueante. Plan es válido DENTRO de límites documentados.
> - **C9 (IMPORTANTE, resuelto):** Retención goldens vaga. Añadido: goldens versionados en repo → histórico indefinido (mejor para auditoría). Alternativa: si se usan como cache de worker, se pueden limpiar manual (documentado).
> - **C10 (IMPORTANTE, resuelto):** F2 dónde está el endpoint de rechazo. Añadido: prerequisito explícito "Plan 54 F4 localiza el endpoint de veredicto". F2 hereda esa ubicación y cableado.
> - **[ADICIÓN ARQUITECTO]:** F0 `Golden.confidence: float | None` — captura el confidence de una épica aprobada para crear goldens positivos condicionales: "si confidence ≥ 0.75, entonces estructura X es esperada". Selectivo: goldens condicionales por banda de confidence..

## Resumen (3 líneas)
- **Qué propone:** cada RECHAZO materializa un golden NEGATIVO (el output no debe volver a exhibir el defecto X) y cada APROBACIÓN un golden POSITIVO; `evaluate_epic_gate` corre contra AMBOS sets versionados, atrapando de forma determinista el defecto que el operador rechazó la vez pasada.
- **Valor:** convierte "memoria guardada" (Plan 54) en comportamiento MEDIDO; cierra el loop de aprendizaje sin LLM (funciones puras), de modo que un defecto rechazado una vez se detecta automáticamente las siguientes.
- **3 runtimes:** todo son funciones puras sobre el HTML de la épica (extractores del Plan 49) → paridad trivial, mismo resultado en los 3 runtimes. Fallback explícito: sin corpus o flag OFF → gate NO-OP (PASS), comportamiento idéntico al actual.

---

## Glosario corto
- **Golden negativo:** patrón determinista (substring/heading ausente/proceso fuera de catálogo) que un output NO debe exhibir, derivado de un rechazo. Si reaparece → defecto.
- **Golden positivo:** patrón que un output aprobado SÍ exhibía y que sirve de baseline de no-regresión (estructura mínima esperada).
- **Gate de regresión:** función pura que, dado el HTML limpio y los dos sets de goldens, devuelve un veredicto (PASS / REPAIR / NEEDS_REVIEW) usando los extractores puros del Plan 49.
- **Corpus:** el conjunto de rechazos/aprobaciones que el Plan 54 F4 garantiza persistir.

## Sustrato verificado (archivo:línea — 2026-06-20)
- `backend/harness/epic_gate.py:72 evaluate_epic_gate(*, clean_html, structural_warnings, process_catalog, catalog_blocking_enabled, looks_like_epic_fn) -> GateVerdict` — veredicto PURO (PASS/REPAIR/NEEDS_REVIEW).
- `backend/harness/epic_gate.py:90-107` — ensamblado: severidades + catálogo + decide blocking. **Punto extensión natural para regresión.**
- Extractores puros Plan 49 (golden-set): disponibles para reusar en clasificación de regresiones.
- **Prerequisito Plan 54 F4 (BLOQUEANTE):** sink rechazo→corpus. Verificar Plan 54 F4 existe.

**Conclusión de sustrato:** `evaluate_epic_gate` es punto único de veredicto. Extensión aditiva: parámetro `regression_goldens` opcional, default None → NO-OP (backward-compatible).

## Rieles no negociables (codificados aquí)
- **Paridad 3 runtimes con fallback:** todo es función pura sobre `clean_html`. Sin corpus → NO-OP. El gate corre igual independientemente del runtime que generó el output.
- **Cero trabajo extra:** los goldens se derivan automáticamente de aprobar/rechazar (acciones que el operador ya hace). Nada nuevo que completar.
- **Human-in-the-loop:** el gate INFORMA (warning) o BLOQUEA (needs_review), no decide por el humano; el humano sigue aprobando/rechazando, y eso ALIMENTA el gate.
- **Mono-operador sin auth:** goldens por (project, agent_type, work_item_type), sin permisos de usuario.
- **No degradar / backward-compatible:** flag `STACKY_REGRESSION_GATE_ENABLED` default OFF; además modo WARNING antes de BLOCKING (patrón plan 50→51).
- **Reusar lo existente:** reusa `evaluate_epic_gate`, los extractores del Plan 49 y el corpus del Plan 54.

---

## Fases

### F0 — Modelo de golden + derivadores puros (heurística substring + condicional confidence)
**Objetivo:** definir golden y funciones que lo derivan de veredicto humano (determinista, sin LLM).

- **Archivo nuevo:** `backend/harness/regression_goldens.py`
- **Símbolos exactos:**
  ```python
  from typing import NamedTuple

  class Golden(NamedTuple):
      kind: str            # "negative" | "positive"
      check: str           # "absent_substring" | "present_heading"
      value: str           # patrón: substring norm. o heading canónico
      project: str | None
      agent_type: str
      work_item_type: str  # "Epic" | "Issue"
      confidence_band: str | None = None  # "low" | "medium" | "high" si es positivo condicional

  def derive_negative_golden(*, rejection_note: str, project, agent_type, work_item_type) -> Golden | None:
      """PURA. nota → golden negativo.
      Heurística (substring-match, no LLM):
        1. nota vacía → None.
        2. value = normalize(note) [lower + collapse whitespace].
        3. check="absent_substring".
      ⚠️ LÍMITE: si nota varía en redacción, no detecta regresión.
      Mitigación: warnings, no bloqueante (default).
      """

  def derive_positive_golden(
      *, clean_html: str, project, agent_type, work_item_type,
      confidence: float | None = None
  ) -> Golden | None:
      """PURA. HTML aprobado → golden positivo.
      Extrae headings estructurales mínimos (p.ej. RF block).
      check="present_heading". Si no hay marcador → None.
      Si confidence ≥ 0.75 → confidence_band="high" (positivo condicional de alta confianza).
      """

  def evaluate_regression(*, clean_html: str, goldens: list[Golden], process_catalog) -> list[str]:
      """PURA. Devuelve defectos de regresión:
        - "regression_negative:<value>" si negativo REAPARECE.
        - "regression_positive_missing:<value>" si positivo FALTA.
      Selectivo: goldens con confidence_band = solo evalúa si confidence actual ≥ banda.
      Sin goldens → [].
      """
  ```
- **Casos borde:**
  - nota/html vacíos → None.
  - Substring matching case-insensitive, normalizado; deduplicar goldens por (kind, check, value).
  - confidence_band=None: golden siempre se evalúa (incondicional).
  - confidence_band="high": solo si confidence ≥ 0.75.
  
- **Tests PRIMERO:** `backend/tests/test_regression_goldens.py`
  - `test_negative_from_note_deterministic` — nota → determinista; vacía → None.
  - `test_positive_from_html_extracts_heading` — HTML → golden positivo con heading.
  - `test_positive_with_high_confidence_adds_band` — confidence ≥0.75 → confidence_band="high".
  - `test_evaluate_detects_negative_reappeared` — golden negativo value en HTML → `regression_negative:...`.
  - `test_evaluate_detects_positive_missing` — heading ausente → `regression_positive_missing:...`.
  - `test_evaluate_skips_conditional_golden_low_confidence` — confidence_band="high" pero actual confidence=0.5 → golden no se evalúa (skip).
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_regression_goldens.py" -q`
- **Aceptación binaria:** 6 tests verdes. **Comando:** arriba, exit 0.
- **Flag:** ninguno (puro).
- **Impacto por runtime:** ninguno aún.
- **Trabajo del operador:** ninguno.

### F1 — Persistencia de goldens (JSON versionado en repo)
**Objetivo:** guardar/cargar goldens por (project, agent_type, work_item_type); versionado en repo para auditoría.

- **Archivo:** `backend/harness/regression_goldens.py` (funciones IO).
- **Store:** JSON versionado en repo `backend/harness/goldens/<project>__<agent>__<type>.json` (no tabla BD; para auditoría durable).
- **Símbolos:**
  ```python
  def save_golden(g: Golden) -> None:
      """Persiste golden idempotente (no duplica por (kind,check,value))."""
  def load_goldens(*, project, agent_type, work_item_type) -> list[Golden]:
      """[] si archivo inexistente o JSON corrupto (no lanza)."""
  ```
- **Casos borde:** archivo inexistente → []; JSON corrupto → [] + log warn; duplicado → no reescribe (dedup por clave).
- **Directorio:** crear `backend/harness/goldens/` en repo (añadir `.gitkeep` si vacío al inicio).
- **Tests:** `backend/tests/test_regression_goldens_store.py`
  - `test_save_then_load_roundtrip` — guardar → cargar → idéntico.
  - `test_save_idempotent_no_duplication` — guardar 2×mismo golden → sigue siendo 1.
  - `test_load_missing_returns_empty` — archivo no existe → [].
  - `test_corrupt_json_returns_empty_no_raise` — JSON roto → [], no lanza.
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_regression_goldens_store.py" -q`
- **Aceptación binaria:** 4 tests verdes. **Comando:** arriba, exit 0.
- **Flag:** ninguno (IO puro).
- **Impacto por runtime:** ninguno aún.
- **Trabajo del operador:** ninguno.
- **Nota:** goldens versionados en repo = histórico indefinido para auditoría. Si se usan como cache, se pueden borrar manual (documentado en README de goldens).

### F2 — Captura: aprobar/rechazar → derivar+guardar golden
**Objetivo:** materializar golden cuando operador aprueba/rechaza (consume hook Plan 54 F4).

**Prerequisito:** Plan 54 F4 implementado (localiza endpoint de veredicto). Ubicación: `grep -rn "needs_review=False\|verdict.*approved\|human_review" backend/api/` identifica el punto.

- **Cambio:** en el mismo endpoint donde Plan 54 F4 escribe la lección:
  - en RECHAZO (verdict="rejected"): `save_golden(derive_negative_golden(rejection_note=note, project=..., agent_type=..., work_item_type=...))` si no es None.
  - en APROBACIÓN (verdict="approved" o "approved_with_notes"): `save_golden(derive_positive_golden(clean_html=_extract_epic_html(run.output), confidence=run.metadata.get("confidence"), ...))` si no es None.
  - `_extract_epic_html` de `api.tickets` (línea ~5406).
  - `confidence` del metadata del run (Plan 44 `grounding_observatory` lo proporciona, en `epic_summary`).

- **Casos borde:** golden None → no guarda; run sin output → no guarda positivo; confidence ausente → derive_positive sin banda.
- **Tests:** `backend/tests/test_regression_capture.py`
  - `test_reject_creates_negative_golden` — rechazar → `load_goldens` devuelve negativo.
  - `test_approve_creates_positive_golden` — aprobar épica → `load_goldens` devuelve positivo.
  - `test_approve_high_confidence_adds_band` — confidence ≥0.75 → golden con confidence_band="high".
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_regression_capture.py" -q`
- **Aceptación binaria:** 3 tests verdes. **Comando:** arriba, exit 0.
- **Flag:** captura SIEMPRE activa (guardar goldens es inocuo si gate está OFF). Backward-compatible.
- **Impacto por runtime:** N/A (post-run).
- **Trabajo del operador:** ninguno.

### F3 — Conectar al gate: `evaluate_epic_gate` corre contra los goldens
**Objetivo:** que el veredicto único incorpore regresión, en modo warning primero.

- **Archivo:** `backend/harness/epic_gate.py:72 evaluate_epic_gate`.
- **Cambio (aditivo, default NO-OP):** nuevo parámetro opcional:
  ```python
  def evaluate_epic_gate(
      *, clean_html, structural_warnings, process_catalog,
      catalog_blocking_enabled, looks_like_epic_fn,
      regression_goldens=None,          # NUEVO: list[Golden] | None
      regression_blocking_enabled=False # NUEVO: flag resuelto por el caller
  ) -> GateVerdict:
  ```
  - Tras calcular `catalog_unknown` (línea 93), añadir:
    ```python
    regression_defects = []
    if regression_goldens:
        from harness.regression_goldens import evaluate_regression
        regression_defects = evaluate_regression(
            clean_html=clean_html, goldens=regression_goldens, process_catalog=process_catalog)
    has_regression = bool(regression_defects)
    blocking = has_block_sev or (bool(catalog_blocking_enabled) and bool(catalog_unknown)) \
               or (bool(regression_blocking_enabled) and has_regression)
    ```
  - Añadir `regression_defects` al `GateVerdict` (extender el NamedTuple con campo `regression_defects: list = []`, backward-compatible por default).
  - **Modo warning:** con `regression_blocking_enabled=False`, los `regression_defects` se reportan pero NO bloquean (solo telemetría/warning), igual que el patrón plan 50→51.
- **Caller:** quien hoy llama `evaluate_epic_gate` (localizar: `grep -rn "evaluate_epic_gate" backend/`) resuelve y pasa:
  - `regression_goldens = load_goldens(...)` si `STACKY_REGRESSION_GATE_ENABLED` ON, si no None.
  - `regression_blocking_enabled = STACKY_REGRESSION_GATE_BLOCKING` (segundo flag, default OFF).
- **Casos borde:** `regression_goldens=None` → comportamiento idéntico al actual (NO-OP). Si `evaluate_regression` lanzara, ya es pura y no lanza.
- **Tests:** `backend/tests/test_epic_gate_regression.py`
  - `test_gate_noop_without_goldens` — sin goldens → veredicto igual al baseline (snapshot del comportamiento previo).
  - `test_gate_reports_regression_warning_not_blocking` — goldens con defecto + blocking_enabled=False → `regression_defects` no vacío, `blocking=False`.
  - `test_gate_blocks_when_blocking_enabled` — mismo + blocking_enabled=True → `blocking=True`, decision NEEDS_REVIEW.
  - `test_gate_pass_when_no_regression` — html limpio respeto a goldens → `regression_defects=[]`.
  - **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_gate_regression.py" -q`
- **Aceptación binaria:** 4 tests verdes + la suite existente de `epic_gate` sin regresión. **Comando:** `.venv\Scripts\python.exe -m pytest "backend/tests/test_epic_gate_regression.py" "backend/tests/test_epic_gate.py" -q` exit 0.
- **Flag:** `STACKY_REGRESSION_GATE_ENABLED` default OFF (carga goldens); `STACKY_REGRESSION_GATE_BLOCKING` default OFF (warning→blocking). Ambos env_only.
- **Impacto por runtime:** el gate corre sobre `clean_html` igual en los 3; mismo veredicto. Fallback: flags OFF → NO-OP.
- **Trabajo del operador:** ninguno.

### F4 — Telemetría + registro en ratchet
**Objetivo:** sellar `regression_defects` en metadata para observabilidad y registrar tests.
- **Cambio:** donde se consume `GateVerdict`, si `regression_defects`, `metadata["regression_defects"] = verdict.regression_defects` (telemetría pasiva).
- **Archivos ratchet:** añadir `test_regression_goldens.py`, `test_regression_goldens_store.py`, `test_regression_capture.py`, `test_epic_gate_regression.py` a `run_harness_tests.ps1` y `.sh`.
- **Aceptación:** meta-test del ratchet (plan 49 F4) verde.
- **Trabajo del operador:** ninguno.

---

## Orden de implementación
F0 → F1 → F2 → F3 → F4. (Requiere Plan 54 F4 ya implementado para el hook de captura.)

## Fuera de scope (dependencias con el top-5)
- **Plan 54** es prerequisito (corpus + hook de veredicto). Este plan NO implementa la captura del rechazo desde cero: extiende el mismo punto.
- **Plan 55 (preview):** ortogonal; el gate corre sobre output, el preview lo muestra. No se acoplan.
- **Plan 57:** independiente.
- No se hace clasificación semántica de defectos con LLM (todo substring/heading determinista).

## DoD
1. `test_regression_goldens.py`, `test_regression_goldens_store.py`, `test_regression_capture.py`, `test_epic_gate_regression.py` verdes.
2. Con flags OFF: `evaluate_epic_gate` se comporta idéntico al baseline (test `test_gate_noop_without_goldens`).
3. Rechazar crea golden negativo; aprobar crea golden positivo (tests F2).
4. Con `STACKY_REGRESSION_GATE_ENABLED` ON + BLOCKING OFF: defectos reportados sin bloquear; con BLOCKING ON: bloquea.
5. Goldens versionados en `backend/harness/goldens/` (revisables por diff).
6. Tests en el ratchet y meta-test verde.
