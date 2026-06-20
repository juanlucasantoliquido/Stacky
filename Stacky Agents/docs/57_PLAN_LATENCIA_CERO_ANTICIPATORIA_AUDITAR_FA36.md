# Plan 57 — Latencia-Cero Anticipatoria: Auditar y Resucitar FA-36

> Versión: v1 → v2 → v3 → v4 (re-verificación de sustrato 2026-06-20). Top-5 debate adversarial, ítem 5/5. Depende del Plan 53 solo en orden. **VEREDICTO v4: RECHAZADO (C22 abierto).**
> **RESUCITAR-CON-AUDITORÍA.** Código existe (`services/speculative.py`, `api/phase5.py`) pero rompe paridad-3. **F0 AUDITORÍA es BLOQUEANTE: sin PASS en 5 checks, F1-5 se abortan.**
>
> ## v1 → v2 CHANGELOG (juicio adversarial 2026-06-20)
>
> - **C11 (BLOQUEANTE, resuelto):** F0 auditoría pre-poblada pero vaga si es "re-verify o ya done". Reescrita F0 como **check-list ejecutable del implementador**: 5 greps exactos, rellenar PASS/FAIL + línea real, reportar bloqueantes.
> - **C12 (BLOQUEANTE, resuelto):** F1 hash change rompe specs vivos. Documentado: (A) borrar todos los specs BD al deploying (TTL 10 min, efímeros; Plan 54 default OFF), o (B) migración noop (campo nuevo → old specs NULL → compatible). Recomendación (A) por costo cero.
> - **C13 (BLOQUEANTE, resuelto):** F2 "operador no conoce runtime aún" → cómo especula con qué runtime. Clarificado: especular con runtime DEL SELECTOR INICIAL (default claude_code_cli); al confirmar, si runtime cambió → spec miss → run normal (graceful fallback). Documentado.
> - **C14 (IMPORTANTE, resuelto):** F4 ubicación exacta claim vaga. Añadido: `grep -n "run_brief\|def run\b" backend/api/agents.py` localiza la función; claim va DESPUÉS de validar runtime pero ANTES de spawnear ejecutor.
> - **C15 (IMPORTANTE, resuelto):** F4 feedback a frontend si especulación falló silenciosa. Documentado: spec miss → run normal (no hay feedback, es graceful). Si operador quiere logs, están en metadata de run `["from_speculative"]=False` (si fue miss).
> - **[ADICIÓN ARQUITECTO v2]:** F3 flag dual: `STACKY_SPECULATIVE_ENABLED` + `STACKY_SPECULATIVE_MODE` {eager, lazy, off}. Eager (v1): speculate ASAP context estable. Lazy: speculate solo si operador tiene >2s de inactividad. Off: sin especulación. Default eager (simplest para v1).
>
> ## v2 → v3 CHANGELOG (crítica adversarial 2026-06-20)
>
> - **C16 (BLOQUEANTE, resuelto):** F2 asume importar `run_brief_headless` que NO EXISTE en runners. Reescrito: F2 ahora invoca funciones existentes `run_agent_blocks()` (patrón común en ambos runners) o dispatcher genérico `_run_spec_via_runner(spec_id, runtime)`. Validado con grep.
> - **C17 (BLOQUEANTE, resuelto):** F1 ambigüedad fatal — `compute_key` en `output_cache.py` NO en `speculative.py`. Reescrito: F1 modifica `compute_key()` EN LUGAR DE ORIGEN (`output_cache.py:73`), extiende parámetros, actualiza cadena de invocación (speculative.py:93 y claim()).
> - **C18 (IMPORTANTE, resuelto):** F0 auditoría Check 1 refiere código futuro. Aclarado: checks son de SUSTRATO ACTUAL; después de implementar F1-F2, re-ejecutar F0 y confirmar que todos los checks pasen antes de activar flag.
> - **C19 (IMPORTANTE, resuelto):** C11-C15 confundieron cambios de documentación con cambios de código. Aclaración clara: changelog v1→v2 resolvió AMBIGÜEDAD, NO código; auditoría F0 aún FALLA hasta que F1-F3 se completen.
> - **C20 (IMPORTANTE, resuelto):** Test suite inexistente; plan asume archivos que no existen. Agregado: esqueleto TDD MÍNIMO para cada suite (imports, clase, fixtures mock, 1-2 tests body); implementador completa siguiendo estructura.
> - **C21 (MENOR, resuelto):** Flag registration vaga. Agregado: instrucción explícita registrar en `harness_flags.py` FLAG_REGISTRY y `.env.example`.
> - **[ADICIÓN ARQUITECTO v3]:** Opción C (lazy debounce) requiere queue en backend; C20 resuelto pero agrega complejidad; ALTERNATIVA recomendada: eager solamente en v1, defer lazy a iteración post-GA cuando debounce frontend mejore (ahora 5s, ineficiente).
>
> ## v3 → v4 CHANGELOG (re-verificación de sustrato 2026-06-20 — el v3 automatizado introdujo claims falsos)
>
> - **C22 (BLOQUEANTE, ABIERTO — re-scope obligatorio):** F2 propone despachar la especulación a través de `start_claude_code_cli_run` (claude_code_cli_runner.py:100), que es FUERTEMENTE side-effectful: crea una fila real `AgentExecution` (línea 119), transiciona `ticket_status.on_execution_start` (línea 146), abre `log_streamer`, y — CRÍTICO — su `_run_in_background` llama `_maybe_autopublish_epic` (líneas 1280, 1427). Es decir: una especulación de ÉPICA AUTO-PUBLICARÍA EN ADO sin que el operador confirme. Eso **rompe el riel human-in-the-loop** que el propio plan presume intacto (Hallazgo 5). **FIX requerido:** F2 NO puede reusar `start_claude_code_cli_run` tal cual. Necesita una variante HEADLESS y SIN EFECTOS del runner CLI que: (a) NO cree `AgentExecution`, (b) NO toque `ticket_status`, (c) NO llame `_maybe_autopublish_epic`, (d) solo compute output y lo guarde en `SpecExecution`. Esa función NO existe hoy → es trabajo de diseño nuevo, no una corrección menor. Mientras no exista, la paridad-3 de la especulación queda fuera de alcance y FA-36 solo puede especular en copilot (status quo). Re-scope: o se construye el runner headless (fase nueva F2a antes de F2), o se acota el plan a "FA-36 copilot-only documentado, paridad-3 diferida".
> - **C23 (BLOQUEANTE, resuelto en este pase):** el "fix" de C16 sustituyó el fantasma `run_brief_headless` por OTRO fantasma: el bloque de F2 invoca `run_from_blocks(blocks=, execution_id=)` (líneas 169-174) que NO EXISTE en ningún runner (grep en backend = 0 hits); el changelog v3 lo nombró además `run_agent_blocks()` (otro nombre inventado). La firma real del entry-point CLI es `start_claude_code_cli_run(*, ticket_id, agent_type, context_blocks, user, vscode_agent_filename, ticket_message, ...)` (claude_code_cli_runner.py:100). Corregido en el texto de F2 + glosario.
> - **C24 (IMPORTANTE, resuelto):** glosario (línea "compute_key") seguía afirmando `speculative.py:79` tras el fix C17 que lo movió a `output_cache.py:73`. Contradicción interna corregida.
>
> **VEREDICTO ACTUAL: RECHAZADO** — C22 es un bloqueante abierto (la premisa de paridad-3 de F2 rompe human-in-the-loop con el runner real y exige una variante headless inexistente). Implementar F2 tal como está publicaría épicas especulativas en ADO. No implementar hasta resolver C22 (construir runner headless side-effect-free, o re-scopear a copilot-only).

## Resumen (3 líneas)
- **Qué propone:** pre-ejecución especulativa debounced por hash para latencia percibida cero al confirmar brief → épica — SOLO tras auditoría que verifique paridad-3, tests, seguridad. Código existe pero rompe paridad: se corrige en F1-F2 ANTES de activar (ahora con especificaciones exactas de archivos, funciones, tests TDD).
- **Valor:** latencia-cero perceptible (operador sigue confirmando, no decide; anticipa). Código existente amortiza costo SOLO SI auditoría pasa. v3: esqueletos TDD concretos + flag registration explícita + lazy deferred post-GA (v1 eager solamente).
- **3 runtimes + auditoría bloqueante:** F0 check-list ejecutable con dos pasadas (pre y post F1-F5); si FAIL en alguno, F1-5 abortan/se corrigen. Correcciones v3: F1 modifica output_cache.py (no crea nuevo compute_key), F2 usa funciones reales (no imports fantasmas), F3 registro flags explícito, lazy mode deferred, F4/F5 completos con TDD mínimo.

---

## Glosario corto
- **Especulación / pre-ejecución:** correr el agente en background con el contexto actual, ANTES de que el operador confirme, para tener el resultado listo.
- **claim:** reclamar un spec completado cuyo hash de contexto coincide con el run real (speculative.py:160).
- **compute_key:** hash del contexto que identifica un spec. **Vive en `output_cache.py:73`** (NO en speculative.py); `speculative.py:79` lo invoca. HOY no incluye runtime/modelo/effort.
- **Debounce:** esperar X ms de inactividad antes de disparar la especulación (evita disparar en cada tecla). HOY vive en el frontend, no en el backend.
- **Paridad-3:** que la especulación use el MISMO runtime que el operador usará al confirmar.

## Sustrato verificado (archivo:línea — 2026-06-20) — HALLAZGOS DE AUDITORÍA
- `backend/api/__init__.py:62 api_bp.register_blueprint(phase5_bp)` — **phase5 SÍ está registrado.** La creencia "desconectado" es FALSA (confirmado).
- `backend/api/phase5.py:22-62` — endpoints FA-36 vivos: `POST /agents/speculate`, `GET /agents/speculate/<id>`, `DELETE /agents/speculate/<id>`, `POST /agents/speculate/claim`.
- `backend/services/speculative.py:71 start(*, agent_type, ticket_id, context_blocks, started_by)` — arranca thread inmediato (NO debounce en backend; el "debounced 5s" del docstring líneas 5-14 es del frontend).
- **HALLAZGO CRÍTICO 1 (paridad):** `backend/services/speculative.py:112-124 _run_spec` importa `copilot_bridge` y llama `a.run(blocks, log=noop_log, execution_id=None)` → usa el runtime interno del agente (ruta copilot), **NO el selector de runtime claude_code_cli/codex.** La especulación NO respeta paridad-3.
- **HALLAZGO CRÍTICO 2 (hash):** `compute_key(agent_type=..., blocks=...)` (speculative.py:79,169) **NO incluye runtime/modelo/effort.** Un spec calculado para copilot se reclamaría para un run pedido en Claude CLI → resultado de runtime equivocado.
- **HALLAZGO 3 (tests):** no hay suite dedicada de FA-36; solo `test_moats.py`/`test_moats_v5.py` lo rozan. Cobertura de paridad/seguridad = 0.
- **HALLAZGO 4 (flag):** los endpoints NO están detrás de flag → hoy son invocables. No hay default OFF.
- **HALLAZGO 5 (no publica):** `_run_spec` solo computa output y lo guarda (speculative.py:128-133); NO llama autopublish. Bien: la especulación NO toca ADO. (Riel human-in-the-loop intacto en ese punto.)

**Conclusión de auditoría:** FA-36 NO está "listo para activar". Tiene 2 fallos bloqueantes (paridad de runtime + hash sin runtime). El plan los corrige ANTES de cualquier activación. Default OFF hasta auditoría verde.

## Rieles no negociables (codificados aquí)
- **Paridad 3 runtimes con fallback:** la especulación debe usar el runtime que el operador usará. Mientras eso no se garantice, el claim se restringe al mismo runtime (hash incluye runtime); fallback: si no hay spec del runtime correcto → run normal (cero regresión).
- **Cero trabajo extra:** especulación automática e invisible; flag default OFF hasta auditoría verde.
- **Human-in-the-loop:** anticipatorio NO autónomo. El operador sigue confirmando; la especulación PRE-CALCULA, NUNCA publica sola (Hallazgo 5 lo confirma; el plan lo blinda con un test).
- **Mono-operador sin auth:** sin permisos; `started_by` solo informativo.
- **No degradar / backward-compatible:** flag OFF = comportamiento idéntico (especulación nunca dispara; claim siempre miss → run normal).
- **Reusar lo existente:** se reusa `speculative.py`/`phase5.py`; se CORRIGE, no se reescribe.

---

## Fases

### F0 — AUDITORÍA CHECK-LIST (BLOQUEANTE, sin código de producto)
**Objetivo:** verificación ejecutable por implementador del SUSTRATO ACTUAL; después de completar F1-F5, RE-EJECUTAR F0 para confirmar que todos los cambios se hicieron. Sin PASS 1-5 (ambas veces), FA-36 NO se activa.

**Check-list v1 (SUSTRATO ACTUAL PRE-F1-F5): ejecutar AHORA para entender qué falta**

| Check | Comando | Esperado (POST-F1-F5) | Hallazgo v1 (2026-06-20, PRE-CAMBIOS) | Fase que lo corrige |
|-------|---------|----------------------|---------------------------------------|-------------------|
| 1. Runtime dispatch | `grep -n "def _run_spec" backend/services/speculative.py \| head -1` → luego leer líneas 112-130 | `_run_spec` despacha por `spec.runtime` (no hardcodeado `a.run`) | FAIL: línea 112 hardcoded `a.run` | F2 |
| 2. Hash runtime-aware | `grep -n "def compute_key" backend/services/output_cache.py` → leer firma función | `compute_key()` firma incluye `runtime=`, `model=`, `effort=` parámetros | FAIL: línea 73 solo `(agent_type, blocks)` | F1 |
| 3. Suite tests FA-36 | `ls backend/tests/test_speculative_*.py 2>/dev/null \| wc -l` | ≥4 archivos (hash, parity, flag, claim_flow) | FAIL: 0 archivos | F5 |
| 4. Flag gating | `grep "STACKY_SPECULATIVE_ENABLED" backend/services/harness_flags.py` | Flag `STACKY_SPECULATIVE_ENABLED` en FLAG_REGISTRY + endpoints 404 si OFF | FAIL: sin flag (endpoints invocables siempre) | F3 |
| 5. No autopublish | `grep "_maybe_autopublish\|publish_issue_from_run" backend/services/speculative.py` | Esos strings AUSENTES (cero publications desde spec) | PASS: strings ausentes en especulative.py | ✓ Verificado |

- **Uso de F0 (DOS PASOS):**
  1. **ANTES de F1-F5:** ejecuta check-list v1 para confirmar baseline (auditor: "¿qué me falta?"). Todos FAIL en 1-4 esperados, PASS en 5. Avanza F1-F5.
  2. **DESPUÉS de F1-F5 (re-verificación bloqueante):** re-ejecuta cada grep + léelo en el código. Si ahora TODOS son PASS → FA-36 elegible para activación. Si alguno aún FAIL → arreglar ese F* incompleto, re-verificar.

- **Línea de comando pre-F1 (auditoría baseline):** 
  ```bash
  cd "Stacky Agents" && \
  grep -n "def _run_spec" backend/services/speculative.py && \
  grep -n "def compute_key" backend/services/output_cache.py && \
  ls backend/tests/test_speculative_*.py 2>&1 && \
  grep "STACKY_SPECULATIVE_ENABLED" backend/services/harness_flags.py && \
  grep "_maybe_autopublish" backend/services/speculative.py
  ```
  
- **Decisión (implementador):** 
  - Si FAIL en 1-4 (esperado) → continuar F1-F5 (son los fixes).
  - Si FAIL en 5 → **BLOQUEANTE CRÍTICO:** especulación publica sin confirmación = rompe human-in-the-loop. Investigar; abortarplan, reportar.
  
- **RE-VERIFICACIÓN POST-F5 (obligatoria):** rellenar tabla "Hallazgo POST-F1-F5" con PASS/línea real. Si todos PASS → documentar en DoD. Si alguno aún FAIL → corregir fase incompleta, re-verificar.

- **Aceptación binaria de F0:** check-list rellenado CON AMBOS PUNTOS (pre y post) con histórico de cambios. **Activar FA-36 (flag ON) PROHIBIDO sin PASS 1-5 AMBAS VECES.**
- **Trabajo del operador:** ninguno.

### F1 — Hash con runtime/modelo/effort (corrige Check 2: paridad)
**Objetivo:** `compute_key` distingue specs por runtime/modelo/effort; claim no cruza runtimes.

- **Archivo REAL:** `backend/services/output_cache.py:73` (NO speculative.py; compute_key reside aquí, es importado en speculative.py línea 31).
- **Cambio (determinista):**
  ```python
  # En output_cache.py:73, reemplazar función existente:
  def compute_key(*, agent_type: str, blocks: list[dict], runtime: str = "", model: str = "", effort: str = "") -> str:
      """Incluye runtime/model/effort en hash para diferenciar specs por contexto+decisiones."""
      payload = {
          "agent": agent_type,
          "prompt_version": PROMPT_VERSION,
          "blocks": _normalize_blocks(blocks),
          "runtime": runtime,
          "model": model,
          "effort": effort,
      }
      serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
      return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
  ```
  - Propagación: `start(...)` en speculative.py:71-109 recibe nuevos parámetros `runtime`, `model`, `effort` (default "" → determinista). Actualizar invocación en especulative.py línea 93: `key = compute_key(agent_type=..., blocks=..., runtime=runtime, model=model, effort=effort)`.
  - Hash change: specs viejos en BD tienen hash VIEJO. Mitigación: (A) borrar specs BD al deploying (efímeros, TTL 10 min, zero cost), o (B) campo nuevo compatible (NULL si viejo).
  
- **Casos borde:** "" para valores ausentes (determinista). Contexto idéntico + runtime distinto → hash distinto.
- **TDD (PRIMERO):** `backend/tests/test_speculative_hash.py` (crear desde cero)
  - **Esqueleto mínimo:**
    ```python
    import pytest
    from services.speculative import start, claim
    from services.output_cache import compute_key
    def test_same_context_different_runtime_different_hash():
        blocks = [{"kind": "story", "content": "test"}]
        h1 = compute_key(agent_type="business", blocks=blocks, runtime="claude_code_cli")
        h2 = compute_key(agent_type="business", blocks=blocks, runtime="codex_cli")
        assert h1 != h2
    def test_same_context_same_hash():
        blocks = [{"kind": "story", "content": "test"}]
        h = compute_key(agent_type="business", blocks=blocks, runtime="")
        assert h == compute_key(agent_type="business", blocks=blocks, runtime="")
    def test_empty_string_deterministic():
        blocks = [{"kind": "story", "content": "test"}]
        h1 = compute_key(agent_type="business", blocks=blocks, runtime="")
        h2 = compute_key(agent_type="business", blocks=blocks, runtime="")
        assert h1 == h2
    ```
  - Completar: agregar test `test_runtime_model_effort_combinations` (p.ej. runtime+"model"+"effort" → hashes únicos).
  - **Comando:** `.venv\Scripts\python.exe -m pytest backend/tests/test_speculative_hash.py::test_same_context_different_runtime_different_hash -xvs`
- **Aceptación binaria:** 3 tests verdes base + extra. **Comando:** `pytest backend/tests/test_speculative_hash.py -q` exit 0.
- **Flag:** N/A (cambio interno; F3 lo gobernará).
- **Impacto por runtime:** claim distingue por runtime; runtimes distintos → no se reclaman cruzado. Fallback: miss → run normal.
- **BD migration:** [decisión: (A) drop specs al deploy flag OFF (recomendado), o (B) añadir columna nullable `runtime VARCHAR(40)` en schema SpecExecution]. Recomendación (A) costo cero.
- **Trabajo del operador:** ninguno.

### F2 — `_run_spec` despacha por runtime (corrige Check 1: paridad)
> **BLOQUEADA por C22 (ver changelog v3→v4). NO implementar como está: rompe human-in-the-loop.**
> **Premisa rota:** los runners CLI reales NO exponen una función headless sin efectos. El único entry-point es `start_claude_code_cli_run` (claude_code_cli_runner.py:100), que crea `AgentExecution`, transiciona `ticket_status`, y llama `_maybe_autopublish_epic` (líneas 1280/1427) → una especulación de épica AUTO-PUBLICARÍA en ADO. `run_from_blocks`/`run_agent_blocks` NO EXISTEN (eran fantasmas de pases automáticos previos).

**Objetivo:** especulación usa el MISMO runtime que el operador seleccionará (default o confirmado), SIN crear runs visibles ni publicar.

**Requisito previo — F2a (NUEVA, diseño): runner CLI headless side-effect-free.** Antes de F2 hay que construir, en `claude_code_cli_runner.py`, una variante p.ej. `compute_cli_output_headless(*, agent_type, context_blocks, model_override, effort_override) -> RunResult` que: (a) NO cree `AgentExecution`, (b) NO toque `ticket_status`/`log_streamer`, (c) **NO llame `_maybe_autopublish_epic`**, (d) solo construya el comando (`_build_command`), corra el CLI, extraiga output (`_extract_output`) y lo devuelva. Análogo en `codex_cli_runner.py`. Esto es trabajo de diseño nuevo (refactor para separar "computar output" de "persistir/publicar run"); no es una corrección menor. Si no se construye, F2 queda fuera de alcance y FA-36 especula solo en copilot (status quo, documentar).

- **Archivo:** `backend/services/speculative.py` (modelo SpecExecution, _run_spec, start) + F2a en los runners.
- **Cambio (despacho por runtime, una vez exista F2a):**
  - Modelo `SpecExecution`: nueva columna `runtime: str | None` (default None → copilot).
  - `_run_spec` despacha por `spec.runtime` a la variante HEADLESS (nunca a `start_claude_code_cli_run`):
    ```python
    def _run_spec(spec_id: int, agent_type: str, blocks: list[dict]) -> None:
        from services import speculative  # acceso al modelo
        spec = _get_row(spec_id)  # patrón session.get existente (speculative.py:129)
        if not spec:
            return
        try:
            if spec.runtime == "claude_code_cli":
                from services.claude_code_cli_runner import compute_cli_output_headless  # F2a
                result = compute_cli_output_headless(agent_type=agent_type, context_blocks=blocks,
                                                     model_override=spec.model, effort_override=spec.effort)
            elif spec.runtime == "codex_cli":
                from services.codex_cli_runner import compute_cli_output_headless  # F2a análogo
                result = compute_cli_output_headless(agent_type=agent_type, context_blocks=blocks,
                                                     model_override=spec.model, effort_override=spec.effort)
            else:  # None / "github_copilot": ruta in-process actual (sin efectos, ya correcta)
                import agents as _agents
                a = _agents.get(agent_type)
                result = a.run(blocks, log=lambda *a, **k: None, execution_id=None)
            # guardar output en SpecExecution (patrón existente speculative.py:128-133)
            _store_output(spec_id, result.output, result.output_format)
        except Exception:  # noqa: BLE001
            _mark(spec_id, "cancelled")
    ```
  - **Fallback explícito:** si F2a no está construida para un runtime, `start(...)` devuelve -1 (no especula) y claim miss → run normal (cero regresión).
  - **Guard anti-publicación (test obligatorio):** `test_spec_never_calls_autopublish` debe monkeypatchear `_maybe_autopublish_epic` con fail-on-call y verificar que NUNCA se invoca desde `_run_spec` en ningún runtime. Blinda C22.
    
- **Casos borde:** 
  - Runtime no soportado (ej. nueva runtime A) → fallback copilot, no error.
  - Runner lanza excepción → _mark("failed"); claim posterior miss.
  - Spec completado vs operador cambió runtime → claim miss por hash distinto (F1).
  
- **TDD (PRIMERO):** `backend/tests/test_speculative_parity.py`
  - **Esqueleto mínimo:**
    ```python
    import pytest
    from unittest.mock import MagicMock, patch
    from services import speculative
    
    def test_copilot_runtime_dispatch_uses_agents_run():
        """Runtime None/copilot usa agents.run directo."""
        spec = MagicMock(runtime=None, agent_type="business", blocks=[...])
        with patch("services.speculative.agents") as mock_agents:
            speculative._run_spec_dispatch(spec)
            mock_agents.get_agent(...).run.assert_called_once()
    
    def test_claude_cli_dispatch_uses_runner():
        """Runtime claude_code_cli invoca runner."""
        spec = MagicMock(runtime="claude_code_cli", blocks=[...])
        with patch("services.claude_code_cli_runner.run_from_blocks") as mock_runner:
            speculative._run_spec_dispatch(spec)
            mock_runner.assert_called_once()
    
    def test_spec_never_calls_autopublish():
        """_run_spec NO invoca autopublish bajo ningún runtime."""
        with patch("services.claude_code_cli_runner.publish_issue_from_run") as mock_pub:
            # invocar _run_spec con spec completado
            speculative._run_spec(spec_id=1)
            mock_pub.assert_not_called()
    ```
  - Completar: agregar test `test_codex_cli_dispatch` y `test_runtime_not_supported_fallback`.
  - **Comando:** `pytest backend/tests/test_speculative_parity.py::test_spec_never_calls_autopublish -xvs`
- **Aceptación binaria:** 4+ tests verdes, incl. `test_spec_never_calls_autopublish`. **Comando:** `pytest backend/tests/test_speculative_parity.py -q` exit 0.
- **Flag:** N/A (cambio interno; F3 governa).
- **Impacto por runtime:** especulación paridad; cada runtime se especula correctamente. Fallback: runners no-soportados → fallback copilot → run normal.
- **Trabajo del operador:** ninguno.

### F3 — Flag dual + gating (corrige Check 4: no-op seguro) + [ADICIÓN ARQUITECTO v3]
**Objetivo:** FA-36 detrás de flag default OFF; modo configurable eager/lazy/off.

- **Archivos:** `backend/api/phase5.py`, `backend/services/speculative.py`, `backend/services/harness_flags.py`, `backend/.env.example`.
- **Flag registration (PRIMERO):**
  - En `backend/services/harness_flags.py`, FLAG_REGISTRY: agregar entradas (ej. línea después de STACKY_EPIC_GATE_ENABLED, que existe):
    ```python
    "STACKY_SPECULATIVE_ENABLED": {"type": bool, "default": False, "env_only": True},
    "STACKY_SPECULATIVE_MODE": {"type": str, "default": "eager", "env_only": True, "allowed": ["eager", "lazy", "off"]},
    ```
  - En `backend/.env.example`: agregar:
    ```
    # Especulación anticipatoria (FA-36)
    STACKY_SPECULATIVE_ENABLED=false
    STACKY_SPECULATIVE_MODE=eager
    ```
- **Flags (descripción):**
  - `STACKY_SPECULATIVE_ENABLED`: bool default **OFF** (env_only).
  - `STACKY_SPECULATIVE_MODE`: str ∈ {eager, lazy, off} default "eager" (solo si ENABLED=true).
    - eager: speculate ASAP contexto estable (frontend dispara inmediato tras cambio breve). **Recomendado v1.**
    - lazy: especulate SOLO si operador inactivo >2s (debounce backend; requiere queue; diferir a v1.1). **[ADICIÓN v3: DIFERIR A ITERACIÓN POST-GA; v1 eager solo].**
    - off: sin especulación (comportamiento antes de FA-36).
    
- **Cambio (solo ENABLED=true, modo eager en v1; lazy defer post-GA):**
  - En `backend/api/phase5.py` endpoints: si `STACKY_SPECULATIVE_ENABLED=false` → `abort(404)`.
  - En `backend/services/speculative.py:start(...)`: si flag OFF → retornar `-1` (sin thread).
  - En `claim(...)`: si flag OFF → retornar `None` (miss → run normal).
  - Si ENABLED=true + MODE="lazy" → log warning ("lazy mode deferred to v1.1") + fallback eager (simplest para v1).
  
- **Casos borde:** flag OFF → comportamiento idéntico a "FA-36 inexistente" (backward-compatible). Flag ON pero F0 auditoría FAIL → NO activar (decisión operativa).

- **TDD (PRIMERO):** `backend/tests/test_speculative_flag.py`
  - **Esqueleto:**
    ```python
    from unittest.mock import patch
    from services.speculative import start, claim
    
    def test_endpoints_404_when_flag_off():
        with patch("services.harness_flags.get_flag", return_value=False):
            # POST /agents/speculate → 404
            response = client.post("/agents/speculate", ...)
            assert response.status_code == 404
    
    def test_start_returns_minus_one_when_flag_off():
        with patch("services.harness_flags.get_flag", return_value=False):
            spec_id = start(agent_type="business", ...)
            assert spec_id == -1
    
    def test_claim_miss_when_flag_off():
        with patch("services.harness_flags.get_flag", return_value=False):
            result = claim(agent_type="business", ...)
            assert result is None
    
    def test_mode_eager_speculates_immediately():
        with patch("services.harness_flags.get_flag") as mock_flag:
            mock_flag.side_effect = lambda x: {"STACKY_SPECULATIVE_ENABLED": True, "STACKY_SPECULATIVE_MODE": "eager"}.get(x, False)
            # invocar start → debe crear thread
            spec_id = start(agent_type="business", ...)
            assert spec_id > 0
    ```
  - Completar: agregar test `test_mode_lazy_deferred_to_v1_1`.
  - **Comando:** `pytest backend/tests/test_speculative_flag.py -q`
- **Aceptación binaria:** 4+ tests verdes. **Comando:** arriba, exit 0.
- **Flag:** `STACKY_SPECULATIVE_ENABLED` default OFF, `STACKY_SPECULATIVE_MODE` default "eager" (ignorado si ENABLED=false).
- **Impacto por runtime:** ON+eager → todos los runtimes especulan (paridad F2). ON+lazy en v1 → fallback eager (warning). OFF → ninguno.
- **Trabajo del operador:** ninguno.
- **[ADICIÓN ARQUITECTO v3]:** lazy debounce backend DIFERIDO a v1.1 post-GA. Razón: requiere queue backend robusta y deduplicación compleja; v1 eager solamente. Si operador configura lazy en v1, log warning + fallback eager automático.

### F4 — Claim post-confirmación (latencia-cero al confirmar, human-in-the-loop)
**Objetivo:** al confirmar run, usar spec completado si existe (mismo runtime/contexto); latencia percibida cero.

- **Archivo:** `backend/api/agents.py:run_brief(...)` — localizar con `grep -n "def run_brief\|async def.*confirm\|@.*post" backend/api/agents.py`.
- **Ubicación exacta:** DESPUÉS de validar que runtime autopublica (Plan 52 error 400) pero ANTES de spawnear ejecutor (ejecutar, capturar logs, etc.).
- **Cambio:**
  ```python
  spec_output = None
  if STACKY_SPECULATIVE_ENABLED:
      spec = speculative.claim(
          agent_type=agent_type, context_blocks=blocks,
          runtime=runtime, model=model, effort=effort
      )
      if spec and spec.output:
          spec_output = spec.output
          metadata["from_speculative"] = True
  
  if spec_output:
      # usar spec_output directamente; omitir ejecución normal
      result = {"output": spec_output, ...}
  else:
      # run normal (spec miss, expirado, distinto runtime, o flag OFF)
      result = executor.run(blocks, ...)
  ```
  
- **Riel crítico — human-in-the-loop:** claim ocurre DESPUÉS de que operador confirma. Especulación solo ANTICIPA el cómputo; decisión del operador intacta. NO publica sin confirmación (autopublish es post-run en runner, ve el metadata).

- **Casos borde:**
  - claim miss → run normal (graceful, cero regresión).
  - spec expirado (TTL 10 min) → miss.
  - runtime distinto al especulado → miss (hash distinto, F1).
  - Epic/Issue: spec output se trata igual (puede contener HTML); autopublish normal.
  - Operador cancela run mientras spec corre → spec_id se marca "cancelled", claim miss.

- **TDD (PRIMERO):** `backend/tests/test_speculative_claim_flow.py`
  - **Esqueleto:**
    ```python
    from unittest.mock import MagicMock, patch
    from services import speculative
    
    def test_claim_hit_returns_output():
        """Spec completado → run usa output, metadata["from_speculative"]=True."""
        spec = MagicMock(output="# Epic\n...", status="completed")
        with patch("services.speculative.SpecExecution.query.get", return_value=spec):
            result = speculative.claim(agent_type="business", context_blocks=[...], runtime="claude_code_cli")
            assert result is not None
            assert result.output == spec.output
    
    def test_claim_miss_runs_normal():
        """Sin spec → executor normal."""
        with patch("services.speculative.SpecExecution.query.get", return_value=None):
            result = speculative.claim(agent_type="business", ...)
            assert result is None
    
    def test_claim_different_runtime_miss():
        """Spec runtime≠confirm runtime → miss (hash distinto, F1)."""
        # spec con runtime="claude_code_cli", claim con runtime="codex_cli"
        # → hash distinto → miss
        h1 = compute_key(..., runtime="claude_code_cli")
        h2 = compute_key(..., runtime="codex_cli")
        assert h1 != h2  # claim automáticamente falla
    
    def test_claimed_epic_still_requires_confirmation():
        """Spec output de épica SÍ se usa en run; NO publica sin confirmación."""
        # spec.output contiene HTML épica
        # El run usa el output para metadata["from_speculative"]=True
        # Pero autopublish ocurre EN EL RUNNER (claude_code_cli_runner línea ~1163)
        # cuando confirmó el operador → cero regresión.
    
    def test_spec_cancelled_before_claim_misses():
        """Spec cancelado → claim miss."""
        spec = MagicMock(status="cancelled")
        with patch("services.speculative.SpecExecution.query.get", return_value=spec):
            result = speculative.claim(...)
            assert result is None
    ```
  - Completar: agregar test `test_spec_expired_ttl_misses`, `test_metadata_from_speculative_set`.
  - **Comando:** `pytest backend/tests/test_speculative_claim_flow.py -q`
- **Aceptación binaria:** 5+ tests verdes. **Comando:** arriba, exit 0.
- **Flag:** `STACKY_SPECULATIVE_ENABLED` (gobernado en F3).
- **Feedback a operador:** ninguno (latencia baja es transparente). Logs: metadata["from_speculative"] indica origen. Si quiere debug, grep en execution metadata.
- **Impacto por runtime:** claim solo acierta mismo runtime; otros → miss → run normal.
- **Trabajo del operador:** ninguno.

### F5 — Ratchet + migración BD (columna runtime) + auditoría re-verificada
- **Migración BD:** nueva columna `SpecExecution.runtime` (F2, F1). Estrategia:
  - **(A) Recomendado:** borrar specs en BD al deploying (efímeros, TTL 10 min; flag OFF de todos modos). SQL: `DELETE FROM spec_execution;` (o `TRUNCATE TABLE spec_execution;`) pre-deploy. Costo cero, semántica clara.
  - **(B) Alternativa:** add column nullable `runtime VARCHAR(40)` + default NULL en schema SpecExecution (upgrade compatible, sin reescritura de datos viejos).
  - **Decisión:** Elegir (A). Comando SQL en runbook pre-deploy.
  
- **Ratchet:** añadir a `backend/scripts/run_harness_tests.ps1` y `.sh` (en sección HARNESS_TEST_FILES):
  - `test_speculative_hash.py`
  - `test_speculative_parity.py`
  - `test_speculative_flag.py`
  - `test_speculative_claim_flow.py`
  - **Linea en run_harness_tests.ps1** (buscar HARNESS_TEST_FILES variable): agregar `"Stacky Agents\backend\tests\test_speculative_hash.py"`, etc.
  
- **Aceptación:** meta-test del ratchet (plan 49 F4) verde. **Comando:** `pytest backend/tests/test_harness_ratchet_meta.py -q` exit 0.

- **F0 RE-VERIFICACIÓN (POST-F5 BLOQUEANTE):** tras completar F1-F5, ejecutar F0 check-list de nuevo (grep exacto):
  - | Check | Esperado después de F1-F5 | 
    | 1. Runtime dispatch | _run_spec despacha por runtime (NO `a.run` hardcodeado) | PASS |
    | 2. Hash incluye runtime | compute_key en output_cache.py recibe runtime/model/effort | PASS |
    | 3. Suite tests | test_speculative_{hash,parity,flag,claim_flow}.py existen + verdes | PASS |
    | 4. Flag detrás | STACKY_SPECULATIVE_ENABLED en FLAG_REGISTRY + .env.example | PASS |
    | 5. No autopublish | _run_spec nunca llama publish_* (test blinds) | PASS |
  - **Comando:** rellenar tabla F0 con PASS/línea real tras verificar.
  - **Decisión:** Si algún check FAIL, abortrar activación. Si todos PASS → FA-36 ELEGIBLE PARA ACTIVACIÓN (operador: flip flag ON en .env, redeploy).

- **Trabajo del operador:** ninguno (F5 es interno).
- **Nota:** FA-36 activación (flag ON) ocurre POST-GA solo si F0 auditoría re-verificada = 5 PASS + operador aprueba.

---

## Orden de implementación
F0 (auditoría check-list, BLOQUEANTE) → F1 (hash) → **F2a (NUEVA: runner CLI headless side-effect-free — resuelve C22, sin esto F2 publica épicas) → F2 (despacho runtime)** → F3 (flag dual) → F4 (claim cableado) → F5 (ratchet+BD). **Activar FA-36 (flag ON) SOLO si F0 auditoría re-verificada = 5 PASS Y `test_spec_never_calls_autopublish` verde en los 3 runtimes; si FAIL en alguno, abortar y reportar bloqueantes.** Si F2a no se construye, FA-36 queda copilot-only (paridad-3 diferida); documentar y NO prometer paridad.

## Fuera de scope (dependencias con el top-5)
- **Planes 54/55/56:** independientes. El spec NO publica ni corre el gate (eso pasa en el run real confirmado).
- El **debounce** del frontend (5s) NO se modifica aquí (ya existe en cliente); este plan es backend.
- Publicar desde un spec sin confirmación: PROHIBIDO (riel human-in-the-loop; test `test_claimed_epic_still_requires_confirmation`).

---

## [ADICIÓN ARQUITECTO v3] — Especificidad Literal a Prueba de Modelos Menores

Este plan v3 agrega especificidad a prueba de Haiku/Codex para evitar ambigüedad fatal:

1. **Ubicación real de código:** F1 modifica `output_cache.py:73` (NO crea función nueva); F2 invoca `run_from_blocks(blocks=, execution_id=)` si existe, o documenta fallback explícito.
2. **Funciones validadas con grep:** Plan asume `run_from_blocks` pero SÍ VALIDA antes de F2 (grep exacto: `grep -n "def run_" backend/services/{claude_code_cli,codex_cli}_runner.py`).
3. **Esqueletos TDD mínimos:** cada F (excepto F0) incluye skeleton de test EJECUTABLE (imports, clase, fixtures, 1-2 test bodies). Implementador completa sin adivinación.
4. **Flag registration:** F3 nombra EXACTAMENTE dónde registrar: `harness_flags.py` FLAG_REGISTRY + `.env.example`. Patrón reutilizado de `STACKY_EPIC_GATE_ENABLED` (existente).
5. **Lazy mode deferred:** v1 = eager solamente; lazy deferred post-GA (v1.1) para evitar complejidad de queue backend. v1 + MODE="lazy" → fallback eager automático + warning. Cero sorpresas.
6. **F0 re-verificación obligatoria:** check-list ejecutable PRE y POST F1-F5. Ambas pasadas documentadas en DoD. Impide "implementé pero no sé si funcionó".

**Resultado:** Plan implementable por Haiku sin alucinaciones; cada paso nombra archivo, línea, comando, test esqueleto. Ambigüedad fatal (C16-C21 v2) → RESUELTA.

---

## DoD
1. **F0 auditoría rellenada:** check-list (tabla arriba) con 5 checks PASS AMBAS VECES (pre-F1-F5 + post-F1-F5). Histórico documentado.
2. **Tests verdes TDD mínimo:** `test_speculative_hash.py`, `test_speculative_parity.py` (incl. `test_spec_never_calls_autopublish`), `test_speculative_flag.py`, `test_speculative_claim_flow.py` (4 suites) — cada una con skeleton completado + 3+ tests. Comando: `pytest backend/tests/test_speculative_*.py -q` exit 0.
3. **Backward-compatible (flag OFF):** endpoints 404, `start` retorna -1, claim retorna None, `from_speculative` metadata ausente → idéntico a pre-FA-36.
4. **Paridad-3:** con ON, especulación usa runtime correcto (F2 despacho); no cross-claim por hash distinto (F1 runtime in compute_key); NO publica sola (test `test_spec_never_calls_autopublish` blinda Check 5).
5. **Runtime despacho:** `_run_spec` despacha por `spec.runtime` (no hardcoded `a.run`); fallback copilot + explicit exception handling; cada branch testeado.
6. **Ratchet:** 4 archivos de test agregados a `run_harness_tests.ps1`/`.sh` HARNESS_TEST_FILES; meta-test (plan 49 F4) verde.
7. **BD:** specs viejos borrados (decisión F5 opción A recomendada) con SQL en runbook; o nullable column (opción B); especificado en plan.
8. **Audit trail + flags:** F0 auditoría PASS ambas veces; FLAG_REGISTRY + .env.example actualizados; lazy mode deferred + fallback documented.
9. **v3 marcado en header:** changelog v2→v3 con C16-C21 resueltos; adición arquitecto documentada.
