# Plan 81 — El golden que nace del tache: lo que el operador BORRA en ADO se vuelve golden NEGATIVO determinista (mitad negativa del aprendizaje bidireccional)

> **Estado:** PROPUESTO v1 (no implementado). Autor: StackyArchitectaUltraEficientCode. Fecha: 2026-07-01.
> **Origen:** ganador único del 5º debate adversarial (`docs/_roadmap/TOP5_2026-07-01_POST80_MITAD_NEGATIVA_GOLDEN.md`),
> promoción de la "burbuja" del debate #4 (`docs/TOP5_2026-06-21_POST61_LOOP_PREVENCION_MUERTO.md` §pieza 2).
> **Pre-requisitos (todos IMPLEMENTADOS y verificados 2026-07-01):**
> - Plan 56 (gate de regresión golden ±): `harness/regression_goldens.py` completo; `evaluate_epic_gate`
>   ya acepta `regression_goldens` + `regression_blocking_enabled` (`harness/epic_gate.py:80-81`); el
>   autopublish ya carga goldens y los pasa al gate (`api/tickets.py:6508-6528`).
> - Plan 60 + supervisión 2026-06-21 (mitad POSITIVA viva): `services/ado_edit_learning.py:161-180` deriva
>   golden positivo desde la edición humana; sweep automático cableado en `app.py:410-417`.
> **Este plan agrega SOLO la mitad NEGATIVA:** `EditDelta.removed_snippets` → goldens negativos. No toca el
> gate, no toca el sweep, no toca los runners.
> Implementable por un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) SIN inferir nada.

---

## 1. Objetivo y KPI

**Objetivo (1 párrafo).** Hoy, cuando el operador corrige a mano una épica publicada en ADO, lo que **agrega**
ya se aprende dos veces (lección blanda + golden positivo, plan 60), pero lo que **borra** se aprende solo una
(lección blanda "Evitá: …", `services/ado_edit_learning.py:49-53`) — es decir, la recurrencia del defecto
depende de que el LLM del próximo run obedezca un texto en el prompt (azar). Este plan convierte cada frase
borrada en un **golden negativo determinista** (`absent_substring`): si el mismo texto reaparece en una épica
futura, el gate de regresión (plan 56) lo marca (`regression_negative:<value>`) y — con el flag de blocking ya
existente — lo **bloquea, garantizado**. Cierra la última arista del loop observar→actuar→aprender→PREVENIR.

**KPI / impacto esperado:**
1. Cada edición humana material con borrados produce ≥0 y ≤5 goldens negativos persistidos automáticamente
   (visible en `LearnResult.negative_goldens_written` y en los JSON de `goldens/`).
2. La reaparición de un texto borrado en una épica futura emite `epic_gate_regression: defects=[regression_negative:...]`
   en `grounding_warnings` (telemetría plan 56 F4, `api/tickets.py:6536-6539`) — y bloquea si
   `STACKY_REGRESSION_GATE_BLOCKING=true`.
3. Con todos los flags OFF (default): comportamiento **byte-idéntico** al actual.

---

## 2. Por qué ahora / gap que cierra

- El flujo flagship auto-publica (plan 41), así que la edición en ADO es la señal humana PRIMARIA — y su
  mitad negativa hoy se evapora en memoria blanda. Verificado firsthand 2026-07-01:
  - `harness/ado_edit_diff.py:20` — `removed_snippets` ya captura las unidades borradas (frases de texto
    plano, ya sin tags: `strip_html_to_text` + `_split_units`).
  - `harness/regression_goldens.py:51-77` — `derive_negative_golden` (PURA) existe; su ÚNICO caller es
    `services/regression_capture.py:43` (nota de rechazo in-app, flujo minoritario).
  - `services/ado_edit_learning.py:161-180` — el bloque 7 deriva SOLO el golden positivo.
- El consumo ya está resuelto: `load_goldens(project, "BusinessAgent", "Epic")` en `api/tickets.py:6513-6517`
  alimenta `evaluate_epic_gate` — un golden negativo guardado con **esas mismas keys** se evalúa sin tocar
  una línea del gate.
- Debates #4 y #5 convergieron en que esta es la única capacidad nueva, barata y determinista pendiente del
  ciclo de prevención.

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** todo el plan es backend-side (sweep + gate); ningún runner se toca. Los runs de
  Codex CLI / Claude Code CLI / GitHub Copilot Pro convergen en los mismos paths backend de publish/autopublish
  que ya consultan el gate. Paridad: N/A-neutral por construcción (se declara por fase igualmente).
- **Cero trabajo extra al operador:** la señal ES su trabajo actual (borrar texto en ADO). Feature opt-in,
  default OFF, editable por UI.
- **Human-in-the-loop:** máximo — la fuente del golden es la corrección humana literal. Nada se auto-publica ni
  se auto-repara distinto a hoy.
- **Mono-operador sin auth:** sin RBAC; los goldens viven en el disco local como hasta ahora.
- **No degradar:** con flag OFF, cero cambios de comportamiento; con flag ON, el modo default del gate sigue
  siendo warning-no-bloqueante (`STACKY_REGRESSION_GATE_BLOCKING` default OFF, `api/tickets.py:5910-5913`).
- **Gotcha FlagSpec (OBLIGATORIO):** el `FlagSpec` nuevo NO lleva argumento `default=` (ni `default=False`).
  Cualquier default no-None rompe `test_default_known_only_for_curated` (lista congelada de 12 keys, plan 63).
- **NO reusar la flag del plan 60** (`STACKY_ADO_EDIT_LEARNING_ENABLED`, env_only=True) como toggle de esto:
  esa gatea el sweep completo; la nueva flag gatea SOLO la derivación negativa y debe ser editable por UI.

---

## 4. Fases

### F0 — Derivador puro: `derive_negative_goldens_from_removed` (TDD)

**Objetivo:** función PURA que convierte `removed_snippets` en una lista filtrada y acotada de goldens
negativos. Entrega el 100% de la lógica nueva testeable sin IO.

**Archivo a editar:** `Stacky Agents/backend/harness/regression_goldens.py`
(agregar DEBAJO de `derive_negative_golden`, antes de `_extract_first_rf_heading`).

**Símbolos nuevos (nombres EXACTOS):**
- Constante `_NEG_FROM_EDIT_MIN_LEN = 15` (chars normalizados mínimos por snippet).
- Constante `_NEG_FROM_EDIT_MAX = 5` (cap de goldens negativos por edición).
- Función `derive_negative_goldens_from_removed`.

**Pseudocódigo exacto:**

```python
_NEG_FROM_EDIT_MIN_LEN = 15  # Plan 81 — snippet normalizado más corto no es señal confiable
_NEG_FROM_EDIT_MAX = 5       # Plan 81 — cap por edición (anti-envenenamiento del catálogo)


def derive_negative_goldens_from_removed(
    *,
    removed_snippets: list,
    edited_text: str,
    project: str | None,
    agent_type: str,
    work_item_type: str,
) -> list:
    """PURA. Plan 81 — snippets borrados por el humano → goldens negativos (absent_substring).

    Guards deterministas, en orden:
      1. snippet normalizado (_normalize) con len < _NEG_FROM_EDIT_MIN_LEN → skip.
      2. snippet aún presente (como substring) en edited_text normalizado → skip
         (fue re-formateo/merge de frases, NO un borrado de contenido).
      3. dedup por valor normalizado dentro de la misma edición.
      4. cap _NEG_FROM_EDIT_MAX, preservando el orden de aparición.
    Lista vacía / None / todo filtrado → []. Nunca lanza.
    """
    edited_norm = _normalize(edited_text or "")
    out: list = []
    seen: set = set()
    for s in (removed_snippets or []):
        v = _normalize(str(s))
        if len(v) < _NEG_FROM_EDIT_MIN_LEN:
            continue
        if v in seen:
            continue
        if v in edited_norm:
            continue
        g = derive_negative_golden(
            rejection_note=str(s),
            project=project,
            agent_type=agent_type,
            work_item_type=work_item_type,
        )
        if g is None:
            continue
        seen.add(v)
        out.append(g)
        if len(out) >= _NEG_FROM_EDIT_MAX:
            break
    return out
```

Nota para el implementador: `derive_negative_golden` normaliza con la MISMA `_normalize`, por lo que
`g.value == v` siempre; no recalcular nada.

**Tests PRIMERO** — archivo nuevo `Stacky Agents/backend/tests/test_plan81_negative_golden_from_edits.py`,
sección F0. Casos (nombres exactos):
1. `test_f0_removed_snippet_becomes_negative_golden` — 1 snippet largo (≥15 chars normalizados) →
   1 Golden con `kind=="negative"`, `check=="absent_substring"`, `value==_normalize(snippet)` y las keys
   `project/agent_type/work_item_type` pasadas.
2. `test_f0_short_snippet_is_skipped` — snippet de <15 chars normalizados (p.ej. `"el proceso"`) → `[]`.
3. `test_f0_snippet_still_present_in_edited_is_skipped` — snippet cuyo texto normalizado sigue como
   substring de `edited_text` → `[]` (re-formateo, no borrado).
4. `test_f0_dedup_within_same_edit` — el mismo snippet dos veces (con distinto casing/espacios) → 1 golden.
5. `test_f0_cap_max_five` — 8 snippets válidos distintos → exactamente 5 goldens, en orden de aparición.
6. `test_f0_empty_and_none_inputs` — `removed_snippets=[]` y `removed_snippets=None` → `[]`; no lanza.
7. `test_f0_pure_and_deterministic` — dos llamadas con los mismos args → resultados iguales (listas iguales).

**Comando (desde `Stacky Agents/backend`, con el venv del repo):**
`.\.venv\Scripts\python.exe -m pytest tests\test_plan81_negative_golden_from_edits.py -q -k f0`

**Criterio binario:** los 7 tests F0 pasan; `pytest tests\test_regression_goldens.py -q` sigue verde (no se
tocó ninguna función existente).
**Flag:** ninguna (función pura sin caller aún; inerte).
**Runtimes:** neutral (código puro backend). **Trabajo del operador:** ninguno.

---

### F1 — Wiring en `learn_from_work_item` (bloque 7b) + `LearnResult.negative_goldens_written`

**Objetivo:** que el sweep existente (plan 60) derive y persista los goldens negativos cuando la flag nueva
esté ON, con las MISMAS keys que lee el gate (anti-huérfano).

**Archivo a editar:** `Stacky Agents/backend/services/ado_edit_learning.py`

**Cambio 1 — `LearnResult`** (línea ~31): agregar campo AL FINAL, con default (backward-compatible; todas
las construcciones del archivo usan keywords):

```python
@dataclass(frozen=True)
class LearnResult:
    learned: bool
    lesson_written: bool
    golden_written: bool
    rev: int | None
    reason: str
    negative_goldens_written: int = 0   # Plan 81
```

**Cambio 2 — getter de flag** (debajo de `_golden_available`, línea ~72), MISMO patrón at-call-time que
`api/tickets.py:5904-5913` (respeta el toggle por UI sin reiniciar):

```python
def _negative_golden_enabled() -> bool:
    """Plan 81 — lee STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED (default OFF) en call time."""
    import os
    return os.getenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "false").strip().lower() in ("1", "true", "on")
```

**Cambio 3 — bloque 7b** (insertar ENTRE el bloque 7 — golden positivo, que termina en la línea ~180 con el
`except` de `logger.warning("learn_from_work_item: golden falló...")` — y el bloque 8 `# 8. Marcar ledger`):

```python
    # 7b. Goldens negativos (plan 81) — lo que el humano BORRÓ no debe reaparecer.
    #     MISMAS keys que lee el gate del autopublish (api/tickets.py:6513-6517):
    #     agent_type="BusinessAgent", work_item_type="Epic" — si no, el golden queda huérfano.
    negative_goldens_written = 0
    try:
        if _negative_golden_enabled() and _golden_available():
            from harness.regression_goldens import (
                derive_negative_goldens_from_removed,
                save_golden,
            )
            for g in derive_negative_goldens_from_removed(
                removed_snippets=delta.removed_snippets,
                edited_text=delta.edited_text,
                project=project_name,
                agent_type="BusinessAgent",
                work_item_type="Epic",
            ):
                save_golden(g)
                negative_goldens_written += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "learn_from_work_item: negative golden falló (no crítico) para WI %s: %s", ado_id, exc
        )
```

**Cambio 4 — return** (línea ~188): agregar `negative_goldens_written=negative_goldens_written,` al
`LearnResult(...)` final. Los `return LearnResult(...)` tempranos (reasons `ado_unavailable`,
`no_human_edit`, `already_learned`, `not_material`) NO se tocan (el default `0` cubre).

**Tests PRIMERO** — mismo archivo de test, sección F1 (reusar el patrón de stubs de
`tests/test_ado_edit_learning.py`: ado_client fake con `fetch_work_item_updates`, monkeypatch de
`harness.regression_goldens._GOLDENS_DIR` a `tmp_path` vía
`monkeypatch.setattr(regression_goldens, "_GOLDENS_DIR", tmp_path)`). Casos:
1. `test_f1_flag_on_persists_negative_golden` — `monkeypatch.setenv("STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED", "true")`;
   edición humana que borra una frase larga → `LearnResult.negative_goldens_written == 1`; y
   `load_goldens(project=<proyecto>, agent_type="BusinessAgent", work_item_type="Epic")` contiene un golden
   `kind=="negative"` con `value==_normalize(frase)`.
2. `test_f1_flag_off_is_noop` — `monkeypatch.delenv(...)` (flag ausente) → `negative_goldens_written == 0`,
   `load_goldens(...)` sin goldens negativos nuevos, y `golden_written`/`lesson_written` se comportan
   EXACTAMENTE igual que antes (no-regresión del bloque 7).
3. `test_f1_save_golden_failure_is_non_fatal` — monkeypatch `save_golden` para que lance → `reason == "ok"`,
   `learned is True`, `negative_goldens_written == 0` (el warning se traga, el ledger se marca igual).
4. `test_f1_learnresult_backward_compatible` — `LearnResult(learned=False, lesson_written=False,
   golden_written=False, rev=None, reason="x")` construye sin pasar el campo nuevo y
   `negative_goldens_written == 0`.

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests\test_plan81_negative_golden_from_edits.py -q -k f1`
**Criterio binario:** 4 tests F1 verdes + `pytest tests\test_ado_edit_learning.py tests\test_ado_edit_sweep.py -q`
sigue verde (no-regresión plan 60).
**Flag:** `STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED`, default OFF (ausencia == off).
**Runtimes:** neutral (sweep backend; ningún runner tocado). **Trabajo del operador:** ninguno (opt-in default off).

---

### F2 — Flag editable por UI + archivos env (regla dura operator-config-always-via-ui)

**Objetivo:** que el operador pueda activar la feature desde el panel de flags del arnés sin tocar archivos.

**Archivos a editar (4):**

1. `Stacky Agents/backend/services/harness_flags.py` — agregar al `FLAG_REGISTRY`, inmediatamente DESPUÉS del
   bloque del plan 60 (después del `FlagSpec` de `STACKY_ADO_SERVICE_IDENTITY`, zona línea ~1700+):

```python
    # ── Plan 81 — Golden negativo desde ediciones humanas en ADO ──────────────
    FlagSpec(
        key="STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED",
        type="bool",
        label="Golden negativo desde ediciones ADO (plan 81)",
        description=(
            "Plan 81 — Si ON, lo que el operador BORRA al editar un WI publicado se convierte en "
            "golden NEGATIVO determinista: el gate de regresión (plan 56) marca su reaparición en "
            "épicas futuras (y bloquea si STACKY_REGRESSION_GATE_BLOCKING=true). Productor: requiere "
            "STACKY_ADO_EDIT_LEARNING_ENABLED=true. Default OFF."
        ),
        group="global",
        env_only=False,
    ),
```

   **PROHIBIDO** pasar `default=` (gotcha `_CURATED_DEFAULTS_ON`, plan 63).

2. `Stacky Agents/backend/services/harness_flags.py` — agregar la key a `_CATEGORY_KEYS["aprendizaje"]`
   (tupla de la línea ~191-195), al final:
   `"STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED",`

3. `Stacky Agents/backend/.env.example` — junto a `STACKY_ADO_EDIT_LEARNING_ENABLED=false` (línea ~241):
   `STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED=false`

4. `Stacky Agents/backend/harness_defaults.env` — junto a la línea ~15 existente:
   `STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED=false`

**NO tocar** `frontend/` — el panel de flags renderiza desde `FLAG_REGISTRY` automáticamente
(`services/harness_flags.py:5-7`).

**Tests PRIMERO** — mismo archivo, sección F2:
1. `test_f2_flag_registered_ui_editable` — en `FLAG_REGISTRY` existe la key con `type=="bool"` y
   `env_only is False`.
2. `test_f2_flag_categorized_aprendizaje` — la key está en `_CATEGORY_KEYS["aprendizaje"]`.
3. `test_f2_flag_has_no_explicit_default` — `spec.default is None` (protege el gotcha del plan 63).

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests\test_plan81_negative_golden_from_edits.py -q -k f2`
**Criterio binario:** 3 tests F2 verdes + `pytest tests\test_harness_flags.py -q` sigue verde (incluye
`test_default_known_only_for_curated` y el test de categorización total).
**Flag:** la misma; default OFF. **Runtimes:** neutral. **Trabajo del operador:** opt-in por UI (default off).

---

### F3 — Test E2E del loop cerrado + no-regresión byte-idéntica

**Objetivo:** demostrar en UN test el círculo completo: borrado humano → golden negativo persistido → el gate
marca la reaparición; y que con flags OFF nada cambia.

**Archivo:** mismo test file, sección F3 (sin código de producción nuevo).

**Casos:**
1. `test_f3_e2e_deleted_text_blocks_recurrence` — (a) correr `learn_from_work_item` (flag ON, goldens dir en
   `tmp_path`) con una edición que borra la frase
   `"El proceso Mul2Bane transfiere los archivos a la carpeta temporal"`; (b) `load_goldens(project=...,
   agent_type="BusinessAgent", work_item_type="Epic")` → contiene el negativo; (c) llamar
   `evaluate_epic_gate(clean_html=<épica futura que REINCLUYE esa frase>, structural_warnings=[],
   process_catalog=None, catalog_blocking_enabled=False, looks_like_epic_fn=lambda h: True,
   regression_goldens=<los cargados>, regression_blocking_enabled=False)` →
   `verdict.regression_defects == [f"regression_negative:{valor_normalizado}"]` y `verdict.blocking is False`
   (modo warning default).
2. `test_f3_e2e_blocking_mode_blocks` — mismo escenario con `regression_blocking_enabled=True` →
   `verdict.blocking is True` y `verdict.decision == GateDecision.NEEDS_REVIEW`.
3. `test_f3_e2e_clean_epic_passes` — épica futura SIN la frase borrada → `regression_defects == []` y
   `decision == GateDecision.PASS`.
4. `test_f3_flags_off_byte_identical` — flag del plan 81 OFF: `learn_from_work_item` sobre la misma edición
   produce `LearnResult` idéntico al pre-plan (campos previos iguales, `negative_goldens_written == 0`) y el
   directorio de goldens queda sin archivos nuevos de kind negative.

**Comando:** `.\.venv\Scripts\python.exe -m pytest tests\test_plan81_negative_golden_from_edits.py -q -k f3`
**Criterio binario:** 4 tests F3 verdes.
**Flag:** las existentes (`STACKY_REGRESSION_GATE_ENABLED`/`_BLOCKING` se pasan RESUELTAS al gate en el test;
no se tocan). **Runtimes:** neutral. **Trabajo del operador:** ninguno.

---

### F4 — Ratchet: registrar el test nuevo en los runners de harness

**Objetivo:** que el meta-test del plan 49 F4 no falle y el archivo quede en la batería estable.

**Archivos a editar (2):**
1. `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar `tests/test_plan81_negative_golden_from_edits.py`
   a la lista `HARNESS_TEST_FILES` (zona línea ~106, orden alfabético-posicional junto a los test_ado_edit_*).
2. `Stacky Agents/backend/scripts/run_harness_tests.ps1` — agregar `"tests/test_plan81_negative_golden_from_edits.py",`
   en la lista espejo (zona línea ~99).

**Criterio binario:** el meta-test de sincronía del ratchet (plan 49 F4, en `tests/`) queda verde; correr
`.\.venv\Scripts\python.exe -m pytest tests\test_plan81_negative_golden_from_edits.py -q` completo → 18 tests verdes.
**Flag:** ninguna. **Runtimes:** neutral. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación (determinista) |
|---|---|
| Falso positivo: el operador borró una frase por REDUNDANTE (no por incorrecta) y el gate marca una épica futura legítima | Modo warning default (`STACKY_REGRESSION_GATE_BLOCKING` OFF, ya existente); guard #2 de F0 (si el contenido sigue en la edición, no es borrado); el defecto solo aparece si el agente reproduce la frase EXACTA normalizada |
| Envenenamiento del catálogo (muchos goldens basura) | `_NEG_FROM_EDIT_MIN_LEN=15` + cap `_NEG_FROM_EDIT_MAX=5` por edición + dedup en F0 + idempotencia de `save_golden` (dedup por `(kind, check, value)`, `regression_goldens.py:166-190`) |
| Snippet borrado con texto sensible queda en el JSON de goldens | Aceptado y documentado: los goldens ya persisten contenido del dominio del WI en disco local (mono-operador); NO se aplica `pii_masker` porque redactar rompería el matching contra HTML futuro |
| Doble derivación entre sweep runs | Ya resuelto por el ledger del plan 60 (`ado_edit_ledger.mark_learned`, idempotencia por `(ado_id, rev)`); el bloque 7b corre dentro del mismo learn idempotente |
| Romper `test_default_known_only_for_curated` | F2 prohíbe `default=` en el FlagSpec y F2-caso-3 lo protege con test |

## 6. Fuera de scope (explícito)

- Paridad GitLab del edit-learning: `services/ado_edit_learning.py` es ADO-coupled (allowlisted en
  `tests/test_no_adoclient_outside_ado_provider.py:22`). Seguimiento futuro: rediseño baseline-local
  (diff del HTML publicado por Stacky vs descripción actual vía TrackerProvider) que evitaría depender del
  historial de revisiones del tracker.
- Poda/cuarentena/expiración de goldens (idea #7 del 5º debate: al cementerio por prematura).
- UI de inspección del catálogo de goldens.
- Cambiar defaults de `STACKY_REGRESSION_GATE_ENABLED` / `_BLOCKING` (siguen OFF).
- Aplicar goldens negativos a work items que no sean Epic (las keys de lectura del gate hoy son
  `BusinessAgent`/`Epic`; extender keys es un plan aparte).

## 7. Glosario (para el modelo menor)

- **Golden:** registro persistido (JSON en `goldens/`) que el gate de regresión evalúa contra cada épica
  nueva. Negativo = "este texto NO debe reaparecer" (`absent_substring`); positivo = "este heading debe
  estar" (`present_heading`).
- **Gate de regresión (plan 56):** paso determinista dentro de `evaluate_epic_gate` que produce códigos
  `regression_negative:*` / `regression_positive_missing:*`; bloquea solo si su flag de blocking está ON.
- **Sweep (plan 60):** loop de fondo (`sweep_recent_runs`, `app.py:410-417`) que relee WIs publicados y llama
  `learn_from_work_item` cuando detecta una edición humana nueva.
- **`EditDelta`:** resultado puro de `diff_edit` (`harness/ado_edit_diff.py:13-21`); `removed_snippets` son
  frases de TEXTO PLANO (sin tags) presentes en el baseline y ausentes en la edición.
- **Autopublish:** publicación backend de la épica sin aprobación in-app (excepción HITL ya decidida); es el
  punto donde el gate consume los goldens (`api/tickets.py:6493-6556`).
- **FlagSpec / FLAG_REGISTRY:** registro de flags del arnés (`services/harness_flags.py`); todo lo que está
  ahí con `env_only=False` aparece editable en la UI sin tocar frontend.
- **Ratchet:** listas `HARNESS_TEST_FILES` en `scripts/run_harness_tests.{sh,ps1}`; un meta-test obliga a
  registrar ahí todo archivo de test nuevo.

## 8. Orden de implementación

1. F0 (derivador puro + 7 tests) — sin dependencias.
2. F1 (wiring + LearnResult + 4 tests) — depende de F0.
3. F2 (flag UI + env files + 3 tests) — depende de F1 (la key ya se lee ahí).
4. F3 (E2E + no-regresión, 4 tests) — depende de F0-F2.
5. F4 (ratchet) — al final.

## 9. Definición de Hecho (DoD) global

- [ ] `pytest tests\test_plan81_negative_golden_from_edits.py -q` → 18/18 verdes (venv del repo).
- [ ] No-regresión: `pytest tests\test_regression_goldens.py tests\test_regression_capture.py
      tests\test_ado_edit_learning.py tests\test_ado_edit_sweep.py tests\test_epic_gate.py
      tests\test_epic_gate_regression.py tests\test_harness_flags.py -q` → verde.
- [ ] Con `STACKY_NEGATIVE_GOLDEN_FROM_EDITS_ENABLED` ausente/OFF: comportamiento byte-idéntico (F3 caso 4).
- [ ] Flag visible y editable en la UI del arnés (categoría "aprendizaje") sin tocar frontend.
- [ ] Meta-test del ratchet verde con el archivo nuevo registrado en `.sh` y `.ps1`.
- [ ] Ningún runner (`claude_code_cli_runner.py`, `codex_cli_runner.py`, `agent_runner.py`) modificado.

---

**Resumen (5 líneas):**
1. Propone convertir lo que el operador BORRA en ADO en goldens negativos deterministas que el gate de
   regresión ya sabe evaluar y (opcionalmente) bloquear.
2. Valor/KPI: cada corrección manual se vuelve barrera permanente; recurrencias visibles en
   `epic_gate_regression` y bloqueables por flag ya existente.
3. Cero trabajo del operador: la señal es su edición actual; feature opt-in default OFF editable por UI.
4. 3 runtimes: neutral por construcción — todo ocurre en el sweep backend y en el gate backend que los tres
   runtimes ya atraviesan; ningún runner se toca.
5. Reusa íntegros los planes 56 (gate+persistencia) y 60 (sweep+diff+ledger): solo agrega 1 función pura,
   1 bloque de wiring, 1 flag y 18 tests.
