# Plan 61 — Blindaje determinista del flujo FUNCIONAL (Task Gate)

> Estado: IMPLEMENTADO (2026-06-21, commit `20f48001`) · **v2 (juzgado — APROBADO-CON-CAMBIOS)**. Tipo: **HARDENING** (NO game-changer — así fue decidido por el operador tras el 3er debate `debatir-top5-evolucion-stacky`, ver `docs/_roadmap/TOP5_2026-06-20_POZO_SECO_POST60_IMPLEMENTAR_BACKLOG.md`, sección "La idea en la burbuja").
> Audiencia de implementación: modelo MENOR (Haiku / Codex / GitHub Copilot Pro). Todo está dado: rutas exactas, símbolos exactos, casos borde, tests primero, comandos exactos. **NO inferir nada.**
> Origen del número: listado de `Stacky Agents/docs/` → NN máximo existente = 60 → este plan = **61**.
>
> **Versión: v1 → v2** (endurecido por juez adversarial 2026-06-21, skill `criticar-y-mejorar-plan`).
> **Estado de implementación:** IMPLEMENTADO (commit `20f48001`, F0..F5). El juez verificó la crítica **firsthand contra el código ya mergeado**: varios hallazgos describen un bug LATENTE que el plan v1 habría inducido en un modelo menor y que el implementador tuvo que sortear por su cuenta (ver C1). La **[ADICIÓN ARQUITECTO]** (test de vocabulario de defectos) es lo único aún NO implementado: queda para el próximo pase de implementación/supervisión.

---

## CHANGELOG v1 → v2 (correcciones del juez)

- **C1 (BLOQUEANTE) resuelto — F2 resolvía `plan_de_pruebas_path` contra la base EQUIVOCADA.** v1 instruía `plan_file = pt_file.parent / plan_rel`. FALSO: la convención del módulo —y la línea inmediatamente posterior al gate (`tickets.py:3921-3922`: `plan_path = repo_root / plan_rel`)— resuelve `plan_de_pruebas_path` relativo a **`repo_root`**, NO a `pt_file.parent`. Un modelo menor siguiendo el plan al pie (que el plan EXIGE: "NO inferir nada") habría resuelto la ruta mal → `plan_de_pruebas_empty` falso-positivo casi siempre → ruido en warning y **BLOQUEO ESPURIO de Tasks legítimas** con blocking ON. El implementador tuvo que DESVIARSE del plan (usó `repo_root`, `tickets.py:3889`), lo que delata que la promesa de literalidad no se cumplía. Reescrito F2: base = `repo_root / plan_rel`.
- **C2 (IMPORTANTE) resuelto — `epic_id_not_numeric` es un defecto MUERTO en el punto de inserción.** El gate corre en `tickets.py:3881`, DESPUÉS del check `[1c]` (`:3672-3699`) que exige `file_epic_id == str(ado_id)` (ado_id es `int` de la URL → siempre dígitos). Al llegar el gate, epic_id ya es numérico o ya se devolvió 400 `PENDING_TASK_EPIC_MISMATCH` (o se normalizó). El código `epic_id_not_numeric` NUNCA dispara. La tabla de Riesgos v1 lo vendía como código "específico y **temprano**" — pero NO es temprano y es inalcanzable. v2: se mantiene en el código como defensa-en-profundidad redundante (subsumido por [1c]) y se BORRA la afirmación "temprano".
- **C3 (IMPORTANTE) resuelto — el KPI sobre-promete "TODO pending-task.json".** El gate es la ÚLTIMA compuerta antes de crear; las rutas que retornan antes ([1a–1d]: mismatch, stale-consumed, idempotencia) NO pasan por él. El KPI v1 ("todo pending-task.json consumido produce un veredicto") es falso para una reconsumición idempotente. Reescrito el KPI: "todo pending-task.json que **llega a la etapa de creación** (no rechazado antes ni servido por idempotencia)".
- **C4 (MENOR) resuelto — drift de refs de línea.** `_epic_gate_enabled` está en `:5498` (no `:5450`); los lectores nuevos quedaron en `:5521`/`:5526`; el gate se insertó en `:3881` (no "~3790"). Refs actualizadas a la realidad verificada.
- **C5 (MENOR) anotado — doble lectura del plan-de-pruebas** (el gate lee el archivo en `:3884-3894` y `:3921-3923` lo vuelve a stat). Optimización opcional, no bloqueante; anotada en Riesgos.
- **[ADICIÓN ARQUITECTO]** Centinela **golden del vocabulario de defectos** (`_ALL_CODES`): un test que congela el conjunto de códigos que el gate puede emitir, para que el ratchet falle si un cambio futuro agrega/borra un código sin actualizar el contrato de telemetría `task_gate.defects` (que el operador y los dashboards consumen). Reusa la filosofía golden/ratchet de los planes 49/56; cero red/LLM, determinista, cero trabajo del operador, paridad-3 trivial. Ver F1 (test `test_defect_vocabulary_is_frozen`).

---

## 1. Título, objetivo y KPI

**Título.** Gate determinista PURO del contrato `pending-task.json` antes de crear la Task hija en ADO (paridad de protección con el flujo épica).

**Objetivo (1 frase).** Hoy todo el stack de calidad determinista (gate, grounding, convergencia, golden, preview) construido en los planes 49–60 vive **solo en el flujo ÉPICA**; el flujo **FUNCIONAL** (FunctionalAgent → `pending-task.json` → `create_child_task` → Task ADO) sólo valida **presencia de claves + idempotencia**, nunca el **VALOR/contenido** del contrato. Este plan agrega un gate determinista PURO (sin LLM, sin red, sin reloj) que valida el contenido del `pending-task.json` y advierte (default) o bloquea (opt-in) ANTES de crear la Task, reusando el patrón puro de `harness/epic_gate.py`.

**Gap concreto (verificado firsthand).** `create_child_task` (`backend/api/tickets.py:3534`) valida: archivo existe (`:3594`), JSON parsea (`:3620`), claves requeridas PRESENTES (`_PENDING_TASK_REQUIRED_FIELDS`, `:3646`), `status` válido (`:3658`), `epic_id` == ado_id de la URL (`:3672`), idempotencia/stale-consumed (`:3722`). **NUNCA valida que los VALORES sean útiles:** `title` puede ser `""`, `rf_id` puede ser `""`, `description_html` puede estar vacío o no citar la RF, y `plan_de_pruebas_path` puede apuntar a un archivo inexistente o vacío. El check de claves (`tickets.py:40-44`) sólo verifica que la clave exista en el dict, no su contenido. El stack de gate de calidad (`tickets.py:5450-5633`, `harness/epic_gate.py`) es **épica-only**.

**KPI binario.** Con `STACKY_TASK_GATE_ENABLED=true`, todo `pending-task.json` que **llega a la etapa de creación** (es decir, no rechazado antes por las validaciones `[1a–1d]` —mismatch, stale-consumed, idempotencia— que retornan temprano) produce un veredicto determinista `task_gate` (en la respuesta JSON y en el SystemLog) que lista los defectos de contenido detectados (`title_empty`, `rf_id_empty`, `plan_de_pruebas_empty`, `description_empty`, `description_missing_rf`, `epic_id_not_numeric`); por default NO bloquea (warning). Con `STACKY_TASK_GATE_BLOCKING=true` (opt-in dentro de opt-in, requiere el anterior), un veredicto `blocking` devuelve 400 `TASK_GATE_BLOCKED` y NO crea la Task. Con `STACKY_TASK_GATE_ENABLED=false` (default), el comportamiento es **byte-idéntico** al actual: cero llamadas nuevas, cero campos nuevos en la respuesta.

---

## 2. Por qué ahora / gap que cierra

El 3er debate evolutivo (`debatir-top5-evolucion-stacky`, post-60) convergió a **0 finalistas game-changer nuevos** (pozo seco): los ejes valiosos ya están implementados (49–57) o formalizados (53/56/58/59/60, 30/31/32), y los nuevos (few-shot positivo, coaching) **ya existen vivos** (`services/few_shot.py` default-ON, `services/coaching.py`). La **única asimetría real** que quedó es que el flujo FUNCIONAL —el que produce el contrato de trabajo REAL del desarrollador— es el menos protegido. Este plan es **hardening explícito**, NO un salto: cierra esa asimetría barato reusando `harness/epic_gate.py`. No inventa alcance: valida el contrato que el `FunctionalAgent` ya está obligado a producir (ver `backend/agents/functional.py:30-39`).

---

## 3. Principios y guardarraíles (no negociables, codificados en cada fase)

- **3 runtimes con paridad — trivial:** `create_child_task` es un endpoint de BACKEND que consume un `pending-task.json` producido por el `FunctionalAgent` **sea cual sea el runtime** (Codex / Claude Code / Copilot). El gate corre en el punto único de consumo → es **runtime-agnóstico por construcción**. No hay rama por runtime, no hace falta fallback por runtime (el gate es parse puro de un dict + un texto).
- **Cero trabajo extra al operador:** flag default **OFF** = byte-idéntico. Opt-in. Sin pasos manuales nuevos, sin nueva config obligatoria.
- **Configurable por UI (regla `operator-config-always-via-ui`):** los flags se registran en `FLAG_REGISTRY` (`backend/services/harness_flags.py:29`) → aparecen en la UI **sin tocar el frontend** (ver docstring `harness_flags.py:5-7`). NO env-only-oculto: el operador los activa desde la UI.
- **Human-in-the-loop intacto:** el gate produce un veredicto que el operador ve; NO auto-publica, NO auto-corrige, NO saca al operador del lazo. En modo blocking, simplemente DEVUELVE un 400 con el motivo y el operador decide.
- **Mono-operador sin auth:** sin RBAC, sin multiusuario.
- **No degradar:** flag OFF → cero llamadas nuevas (byte-idéntico, verificable por test). El gate es O(tamaño del payload), sin red ni disco dentro de la función pura (el disco lo lee el caller y le pasa el texto).
- **Reuso obligatorio:** mirror EXACTO del patrón de `harness/epic_gate.py` (`GateDecision`/`GateVerdict`/funciones puras `evaluate_*`); reuso de constantes existentes (`_PENDING_TASK_REQUIRED_FIELDS`, `PENDING_TASK_STATUS_CANONICAL`); patrón de lector de flag idéntico a `_epic_gate_enabled` (`tickets.py:5498`); patrón de ratchet idéntico a planes 54/55/57 (`scripts/run_harness_tests.ps1`).

---

## 4. Fases F0..F5

### F0 — Flags (default OFF) + lectores, registrados en la UI

**Objetivo.** Declarar los dos flags y sus lectores, default OFF, visibles en la UI. Valor: el operador puede encender el gate desde la UI sin tocar código.

**Archivos a editar:**
- `backend/services/harness_flags.py` — agregar 2 `FlagSpec` a `FLAG_REGISTRY` (tupla que arranca en `:29`). Insertar justo DESPUÉS del bloque `STACKY_EPIC_CATALOG_GATE_ENABLED` (termina en `:1300`), para agrupar los gates.
- `backend/api/tickets.py` — agregar 2 lectores junto a `_epic_gate_enabled` (`:5498`; verificado: los nuevos lectores quedaron en `:5521`/`:5526`).

**Diff ilustrativo (harness_flags.py, dentro de FLAG_REGISTRY):**
```python
    FlagSpec(
        key="STACKY_TASK_GATE_ENABLED",
        type="bool",
        label="Gate determinista del flujo funcional (Task)",
        description=(
            "Plan 61 — Si ON, al consumir un pending-task.json se valida el "
            "CONTENIDO del contrato (title/rf_id/description/plan-de-pruebas) y "
            "se adjunta un veredicto task_gate en la respuesta/log. Warning, NO "
            "bloquea. Default OFF (byte-idéntico)."
        ),
        group="global",
        env_only=True,  # se lee con os.getenv en api/tickets.create_child_task
    ),
    FlagSpec(
        key="STACKY_TASK_GATE_BLOCKING",
        type="bool",
        label="Bloqueo del flujo funcional (Task)",
        description=(
            "Plan 61 — Si ON (requiere STACKY_TASK_GATE_ENABLED), un veredicto "
            "task_gate blocking devuelve 400 TASK_GATE_BLOCKED y NO crea la Task. "
            "Opt-in dentro de opt-in. Default OFF."
        ),
        group="global",
        env_only=True,
    ),
```

**Diff ilustrativo (tickets.py, junto a `_epic_gate_enabled`):**
```python
def _task_gate_enabled() -> bool:
    """Plan 61 F0 — lee STACKY_TASK_GATE_ENABLED (default OFF)."""
    return os.getenv("STACKY_TASK_GATE_ENABLED", "false").strip().lower() == "true"


def _task_gate_blocking() -> bool:
    """Plan 61 F0 — lee STACKY_TASK_GATE_BLOCKING (default OFF). Requiere el anterior."""
    return os.getenv("STACKY_TASK_GATE_BLOCKING", "false").strip().lower() == "true"
```

**Tests PRIMERO.** Archivo: `backend/tests/test_task_gate_flags.py`. Casos:
- `test_task_gate_disabled_by_default`: sin env var, `_task_gate_enabled()` == False.
- `test_task_gate_blocking_disabled_by_default`: sin env var, `_task_gate_blocking()` == False.
- `test_task_gate_enabled_reads_env`: con `monkeypatch.setenv("STACKY_TASK_GATE_ENABLED","true")`, == True.
- `test_flags_registered_in_registry`: `STACKY_TASK_GATE_ENABLED` y `STACKY_TASK_GATE_BLOCKING` están en `{f.key for f in FLAG_REGISTRY}` (garantiza visibilidad UI).

**Comando exacto (desde `Stacky Agents/backend`, intérprete del venv del repo):**
`.venv\Scripts\python.exe -m pytest tests/test_task_gate_flags.py -q`

**Criterio binario.** 4 passed / 0 failed.
**Flag que la protege.** Las propias flags; default OFF.
**Impacto por runtime.** Idéntico en los 3 (backend). **Trabajo del operador:** ninguno (default OFF; opt-in por UI).

---

### F1 — Módulo PURO `harness/task_gate.py` (mirror de epic_gate.py)

**Objetivo.** Funciones puras testeables que clasifican el contrato del Task en un veredicto determinista. Valor: el núcleo de validación, sin disco/red/LLM, idéntico para los 3 runtimes.

**Archivo a crear:** `backend/harness/task_gate.py`.

**Contrato EXACTO (mirror de `harness/epic_gate.py:20-31`):**
```python
"""Plan 61 — Gate determinista del contrato pending-task.json (flujo funcional).

Funciones PURAS sobre el dict ya parseado del pending-task.json y el TEXTO ya
leído del plan-de-pruebas. Sin LLM, sin red, sin reloj, sin locale, sin datos
personales. Determinismo total. El caller (api/tickets.create_child_task) lee el
disco y le pasa el texto: este módulo NUNCA toca el filesystem.

Los 3 runtimes consumen este módulo idéntico (el gate corre en backend, no por
runtime).
"""
from __future__ import annotations

import re
from enum import Enum
from typing import NamedTuple


class TaskGateDecision(str, Enum):
    PASS = "pass"
    REPAIR = "repair"               # defecto de forma: re-emit barato del agente
    NEEDS_REVIEW = "needs_review"   # contenido faltante: el operador debe mirar


class TaskGateVerdict(NamedTuple):
    decision: TaskGateDecision
    defects: list      # códigos string deterministas, sorted
    blocking: bool     # True si NO debe crear la Task tal cual (solo si blocking flag ON)


# severidad por código de defecto
_REPAIRABLE = frozenset({"title_empty", "description_empty", "description_missing_rf"})
# (el resto → needs_review)
_ALL_CODES = (
    "title_empty", "rf_id_empty", "description_empty",
    "description_missing_rf", "plan_de_pruebas_empty", "epic_id_not_numeric",
)


def _is_blank(v) -> bool:
    """PURA. True si v es None o str vacío/solo-espacios o no-str falsy."""
    if v is None:
        return True
    return not str(v).strip()


def classify_task_defects(payload: dict, plan_de_pruebas_text) -> dict:
    """PURA. payload = dict del pending-task.json; plan_de_pruebas_text = contenido
    ya leído (str) o None si no se pudo leer/no existe. Devuelve {code: severity}
    con orden estable. NUNCA lanza."""
    codes: set[str] = set()
    title = payload.get("title")
    rf_id = payload.get("rf_id")
    desc = payload.get("description_html")
    epic_id = payload.get("epic_id")

    if _is_blank(title):
        codes.add("title_empty")
    if _is_blank(rf_id):
        codes.add("rf_id_empty")
    if _is_blank(desc):
        codes.add("description_empty")
    elif not _is_blank(rf_id) and str(rf_id).strip() not in str(desc):
        # la descripción no menciona la RF que dice cubrir
        codes.add("description_missing_rf")
    if _is_blank(plan_de_pruebas_text):
        codes.add("plan_de_pruebas_empty")
    # epic_id debe ser numérico (System.Id real), no etiqueta humana EP-26/RF-001
    if not _is_blank(epic_id) and not str(epic_id).strip().isdigit():
        codes.add("epic_id_not_numeric")

    return {c: ("repair" if c in _REPAIRABLE else "needs_review") for c in sorted(codes)}


def evaluate_task_gate(
    *,
    payload: dict,
    plan_de_pruebas_text,
    blocking_enabled: bool,
) -> TaskGateVerdict:
    """PURA. Ensambla el veredicto. NUNCA lanza.
      1. defects = classify_task_defects(payload, plan_de_pruebas_text).
      2. blocking = blocking_enabled AND hay alguna severidad 'needs_review'.
      3. decision: blocking -> NEEDS_REVIEW; elif hay 'repair' -> REPAIR; else PASS.
    """
    defects = classify_task_defects(payload, plan_de_pruebas_text)
    has_block_sev = any(v == "needs_review" for v in defects.values())
    blocking = bool(blocking_enabled) and has_block_sev
    if blocking:
        decision = TaskGateDecision.NEEDS_REVIEW
    elif any(v == "repair" for v in defects.values()):
        decision = TaskGateDecision.REPAIR
    else:
        decision = TaskGateDecision.PASS
    return TaskGateVerdict(
        decision=decision,
        defects=sorted(defects.keys()),
        blocking=blocking,
    )
```

**Tests PRIMERO.** Archivo: `backend/tests/test_task_gate.py`. Casos (todos sin disco, payloads literales):
- `test_clean_payload_passes`: payload con todos los campos llenos + plan_text no vacío + epic_id="267" → `decision==PASS`, `defects==[]`, `blocking==False`.
- `test_title_empty_is_repair`: title="" → `"title_empty" in defects`, decision REPAIR (no blocking aunque blocking_enabled=True, porque es repair).
- `test_rf_id_empty_is_needs_review`: rf_id="  " → `"rf_id_empty" in defects`; con `blocking_enabled=True` → `blocking==True`, decision NEEDS_REVIEW.
- `test_plan_de_pruebas_empty`: plan_de_pruebas_text=None → `"plan_de_pruebas_empty" in defects`, needs_review.
- `test_description_missing_rf`: rf_id="RF-003", description sin "RF-003" → `"description_missing_rf" in defects` (repair).
- `test_epic_id_human_label`: epic_id="EP-26" → `"epic_id_not_numeric" in defects` (needs_review).
- `test_epic_id_numeric_ok`: epic_id="267" → `"epic_id_not_numeric" not in defects`.
- `test_blocking_disabled_never_blocks`: payload con needs_review pero `blocking_enabled=False` → `blocking==False`, decision NEEDS_REVIEW NO se fuerza (sigue siendo NEEDS_REVIEW solo si hay sev needs_review… ojo: con blocking=False la decisión cae a REPAIR/PASS). **Aclaración determinista:** la decisión NEEDS_REVIEW SÓLO se emite cuando `blocking==True`. Con `blocking_enabled=False`, un defecto needs_review NO bloquea y la decisión es REPAIR (si hay algún repair) o PASS; el defecto SÍ aparece en `defects` (para el warning).
- `test_never_raises_on_garbage`: payload={} y plan_text=None → no lanza, devuelve veredicto con varios defects.
- `test_determinism_sorted`: dos llamadas idénticas → mismo `defects` (lista sorted estable).
- `test_defect_vocabulary_is_frozen` **[ADICIÓN ARQUITECTO]**: `set(_ALL_CODES)` == el conjunto literal congelado `{"title_empty", "rf_id_empty", "description_empty", "description_missing_rf", "plan_de_pruebas_empty", "epic_id_not_numeric"}`; y, sobre ≥5 payloads basura variados, `classify_task_defects` NUNCA emite un código fuera de `_ALL_CODES`. Blinda el contrato de telemetría `task_gate.defects` (consumido por operador/dashboards) contra erosión silenciosa — filosofía golden/ratchet de los planes 49/56. **(Aún NO implementado: pendiente del próximo pase de implementación/supervisión.)**

**Comando exacto:** `.venv\Scripts\python.exe -m pytest tests/test_task_gate.py -q`
**Criterio binario.** 11 passed / 0 failed (incluye el centinela de vocabulario [ADICIÓN ARQUITECTO]).
**Flag.** N/A (módulo puro; lo gobierna el caller). **Impacto runtime.** Idéntico (módulo importado igual por los 3). **Trabajo del operador:** ninguno.

---

### F2 — Wiring en `create_child_task` (warning + blocking opt-in), byte-idéntico con flag OFF

**Objetivo.** Llamar al gate en el punto de consumo, adjuntar el veredicto y, si blocking, devolver 400. Valor: la protección efectiva, sin sacar al operador del lazo.

**Archivo a editar:** `backend/api/tickets.py`, función `create_child_task` (`:3534`). Punto de inserción (verificado: el gate quedó en `:3880-3919`): DESPUÉS del bloque `[1d] idempotencia` y del check `[1c]` (`:3672`, después de resolver `pt_payload` definitivo), y ANTES del bloque `dry_run`/creación real del work item. Esto garantiza que el gate ve el `pt_payload` ya normalizado. **OJO (C2):** como corre tras `[1c]`, `epic_id` ya está forzado a ser numérico (`== ado_id`) → el defecto `epic_id_not_numeric` es **inalcanzable** en este punto (queda como defensa-en-profundidad redundante, NO como telemetría temprana).

**Pseudocódigo del bloque nuevo (`[1e] Gate de contenido — Plan 61`):**
```python
# ── [1e] Gate determinista de contenido (Plan 61) ──────────────────────────
task_gate_result = None
if _task_gate_enabled():
    from harness.task_gate import evaluate_task_gate
    # Leer el plan-de-pruebas de forma DEFENSIVA (nunca rompe el flujo).
    plan_text = None
    try:
        plan_rel = str(pt_payload.get("plan_de_pruebas_path") or "").strip()
        if plan_rel:
            # C1 — `plan_de_pruebas_path` es relativo a `repo_root` (convención del
            # módulo; ver `tickets.py:3921-3922` `plan_path = repo_root / plan_rel`),
            # NO a `pt_file.parent`. Resolver mal la base produce un
            # `plan_de_pruebas_empty` FALSO (y, con blocking ON, un 400 espurio).
            plan_file = (repo_root / plan_rel) if not Path(plan_rel).is_absolute() else Path(plan_rel)
            if plan_file.is_file():
                plan_text = plan_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        plan_text = None  # ante cualquier error de disco, lo tratamos como ausente
    _verdict = evaluate_task_gate(
        payload=pt_payload,
        plan_de_pruebas_text=plan_text,
        blocking_enabled=_task_gate_blocking(),
    )
    task_gate_result = {
        "decision": _verdict.decision.value,
        "defects": _verdict.defects,
        "blocking": _verdict.blocking,
    }
    logger.info(
        "create_child_task: task_gate operation_id=%s ado_id=%s decision=%s defects=%s blocking=%s",
        operation_id, ado_id, _verdict.decision.value, _verdict.defects, _verdict.blocking,
    )
    if _verdict.blocking and not dry_run:
        return jsonify({
            "ok": False,
            "error": "TASK_GATE_BLOCKED",
            "task_gate": task_gate_result,
            "message": (
                "El contrato pending-task.json tiene defectos de contenido no "
                f"reparables: {_verdict.defects}. Corregí el archivo o desactivá "
                "STACKY_TASK_GATE_BLOCKING."
            ),
            "correlation_id": correlation_id,
            "operation_id": operation_id,
        }), 400
```
- Luego, en el `return jsonify({...})` de ÉXITO de la función (el payload de respuesta OK), agregar `"task_gate": task_gate_result` (será `None` si el flag está OFF → no cambia nada perceptible salvo una clave null; **alternativa byte-idéntica:** incluir la clave solo si `task_gate_result is not None`). **Decisión determinista:** incluir la clave SÓLO si `task_gate_result is not None`, para garantizar respuesta byte-idéntica con flag OFF.
- Usar los símbolos REALES ya en scope: `repo_root` ya está disponible dentro de `create_child_task` (se usa en `:3921`) y `Path` ya está importado al tope de `tickets.py`. **NO usar `pt_file.parent` como base** (C1) ni inventar alias `_Path`/`_os`.

**Tests PRIMERO.** Archivo: `backend/tests/test_create_child_task_gate.py`. Usar el patrón de fixtures de `tests/test_create_child_task_endpoint.py` (cliente Flask + AdoClient fake + tmp_path con pending-task.json). Casos:
- `test_gate_off_response_byte_identical`: sin flag → la respuesta OK NO contiene la clave `task_gate`.
- `test_gate_on_warning_attaches_verdict`: `STACKY_TASK_GATE_ENABLED=true`, payload con `title=""` → respuesta OK (200/idempotente) contiene `task_gate.defects` con `"title_empty"` y NO bloquea (Task se crea).
- `test_gate_blocking_rejects`: ambos flags ON, payload con `rf_id=""` (needs_review) → 400 `TASK_GATE_BLOCKED`, AdoClient.create_work_item NO fue llamado.
- `test_gate_blocking_dry_run_does_not_block`: ambos flags ON + `dry_run=true` → NO devuelve 400 (dry_run nunca bloquea), adjunta el veredicto.
- `test_gate_plan_de_pruebas_missing_file`: flag ON, `plan_de_pruebas_path` apunta a archivo inexistente → defecto `plan_de_pruebas_empty`.
- `test_gate_clean_payload_passes`: flag ON, payload completo + plan-de-pruebas no vacío + epic_id numérico → `task_gate.decision=="pass"`, Task creada.

**Comando exacto:** `.venv\Scripts\python.exe -m pytest tests/test_create_child_task_gate.py -q`
**Criterio binario.** 6 passed / 0 failed.
**Flag.** `STACKY_TASK_GATE_ENABLED` (warning) + `STACKY_TASK_GATE_BLOCKING` (blocking); ambos default OFF.
**Impacto por runtime.** Idéntico en los 3 (endpoint backend). **Fallback:** ninguno necesario (no es per-runtime). **Trabajo del operador:** ninguno (default OFF).

---

### F3 — Observabilidad: el veredicto en el SystemLog de auditoría

**Objetivo.** Que el `task_gate` quede en el registro de auditoría que `create_child_task` ya escribe (paso [7] SystemLog), para que el operador lo vea en el historial sin endpoint nuevo. Valor: trazabilidad sin trabajo nuevo.

**Archivo a editar:** `backend/api/tickets.py` — en el armado del `SystemLog`/auditoría de `create_child_task` (buscar el `SystemLog(` o `system_logs` dentro de la función, paso [7] descrito en el docstring `:3544`), agregar `task_gate` al dict de detalle SI `task_gate_result is not None`.

**Pseudocódigo:**
```python
audit_detail = { ... }  # dict existente
if task_gate_result is not None:
    audit_detail["task_gate"] = task_gate_result
```

**Tests PRIMERO.** Extender `test_create_child_task_gate.py` con:
- `test_gate_verdict_in_system_log`: flag ON + payload con defecto → el SystemLog persistido contiene `task_gate` con los defects. (Reusar el patrón de aserción sobre `system_logs` de `tests/test_create_child_task_endpoint.py`.)

**Comando exacto:** `.venv\Scripts\python.exe -m pytest tests/test_create_child_task_gate.py -q`
**Criterio binario.** test nuevo PASS (7 passed / 0 failed acumulado con F2).
**Flag.** misma de F2. **Impacto runtime.** Idéntico. **Trabajo del operador:** ninguno.

---

### F4 — Centinela de NO-regresión (flag OFF = byte-idéntico)

**Objetivo.** Test que clava que con ambos flags OFF, `create_child_task` se comporta EXACTAMENTE como antes (cero clave `task_gate`, cero llamada a `harness.task_gate`). Valor: garantiza backward-compat para siempre.

**Archivo a editar:** `backend/tests/test_create_child_task_gate.py` — agregar:
- `test_no_import_of_task_gate_when_disabled`: con flag OFF, mockear/espiar `harness.task_gate.evaluate_task_gate` y afirmar que NO fue llamado.
- `test_existing_endpoint_tests_still_green`: (meta) correr la suite existente `tests/test_create_child_task_endpoint.py` y confirmar 0 regresiones.

**Comando exacto:**
`.venv\Scripts\python.exe -m pytest tests/test_create_child_task_gate.py tests/test_create_child_task_endpoint.py -q`
**Criterio binario.** Toda la suite de ambos archivos verde (0 failed).
**Flag.** N/A (verifica el default OFF). **Impacto runtime.** Idéntico. **Trabajo del operador:** ninguno.

---

### F5 — Ratchet: registrar los tests nuevos en el arnés

**Objetivo.** Que `test_task_gate.py`, `test_task_gate_flags.py` y `test_create_child_task_gate.py` entren al ratchet del arnés (igual que hicieron 54/55/57), para que una regresión futura los corra siempre. Valor: el blindaje no se erosiona.

**Archivo a editar:** `scripts/run_harness_tests.ps1` — agregar las 3 rutas a la lista de tests del ratchet (mismo bloque donde están `test_epic_gate.py`, `test_memory_prefix.py`, etc.). Buscar el array/listado existente y append.

**Tests / verificación.** Correr el script del ratchet y confirmar que incluye y pasa los 3 archivos:
`powershell -File scripts/run_harness_tests.ps1` (o el comando que el repo ya use; si el script toma `-Only`, verificar que los 3 archivos figuran en la lista). 
**Criterio binario.** El script lista y ejecuta los 3 nuevos archivos con 0 failed.
**Flag.** N/A. **Impacto runtime.** Idéntico. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El gate bloquea Tasks legítimas (falsos positivos) | Default OFF + blocking es opt-in dentro de opt-in; warning-mode primero. El operador prueba en warning, observa los defects en el log, y recién enciende blocking si confía. |
| Lectura del `plan_de_pruebas` rompe el flujo por error de disco/encoding | Acceso 100% defensivo (`try/except` → `plan_text=None`); el error de disco se trata como "plan ausente" (defecto, no excepción). El gate NUNCA lanza. |
| `epic_id_not_numeric` es INALCANZABLE en el punto de inserción (el gate corre tras `[1c]`, que ya exige `epic_id == ado_id` numérico) | **Verificado (C2):** al llegar el gate, epic_id ya es numérico, o ya se devolvió 400 `PENDING_TASK_EPIC_MISMATCH`, o se normalizó. Se mantiene SÓLO como defensa-en-profundidad redundante ante un futuro refactor de `[1c]`; NO es "temprano" ni aporta telemetría nueva hoy. No cambia el comportamiento de `[1c]`. |
| Doble lectura del `plan_de_pruebas` (C5): el gate lo lee en `:3884-3894` y `:3921-3923` lo vuelve a stat | Menor (no es hot-path; el flujo crea UNA Task por request). Optimización opcional: computar `plan_text`/`plan_exists` una sola vez y reusar. No bloqueante. |
| Cambiar la respuesta JSON rompe consumidores | Con flag OFF la clave `task_gate` NO se agrega (byte-idéntico, test F4). Con flag ON, es una clave NUEVA opcional (aditiva, backward-compatible). |
| Acoplar el gate a un runtime | Imposible: corre en `create_child_task` (backend), después de que cualquier runtime escribió el archivo. Parity-3 por construcción. |

## 6. Fuera de scope (NO implementar en este plan)
- **Aviso en tiempo de GENERACIÓN al FunctionalAgent** (validar el archivo apenas el agente lo escribe). El agente corre headless y escribe a disco; un validador post-escritura (vía `output_watcher`) es otro plan. Acá el gate vive en el ÚNICO chokepoint de consumo, que alcanza y es runtime-agnóstico.
- **Auto-corrección del `pending-task.json`** (reescribir el archivo). Violaría human-in-the-loop y mecánica de idempotencia. El gate sólo ADVIERTE/BLOQUEA; el operador corrige.
- **Bucle de convergencia para el Task** (análogo al plan 58 de épica). Depende de un re-emit del agente; fuera de este hardening.
- **Gate de catálogo/grounding sobre el Task.** El `pending-task.json` no cita procesos del catálogo como la épica; no aplica.
- **Superficie del veredicto en el triage de Salud Operativa (plan 46) / `needs_review`.** Mostrar `task_gate.defects` en `OperationalHealthCard` para que el modo warning sea visible sin leer logs es valioso, pero toca frontend y agrega alcance → queda como **hook futuro explícito**, NO en este hardening.

## 7. Glosario (términos Stacky para un modelo menor)
- **pending-task.json:** contrato en disco que el `FunctionalAgent` deja para que Stacky cree una Task hija en ADO. Campos obligatorios en `_PENDING_TASK_REQUIRED_FIELDS` (`tickets.py:40`). El agente NUNCA escribe en ADO; sólo deja el archivo (ver `agents/functional.py:25-39`).
- **create_child_task:** endpoint backend (`tickets.py:3534`) que CONSUME el `pending-task.json` y crea la Task en ADO. Único punto autorizado a escribir esa Task.
- **RF / rf_id:** Requisito Funcional; un Epic se descompone en bloques RF-XXX. El Task cubre una RF.
- **System.Id:** id numérico REAL del work item en Azure DevOps (ej. `267`). NO confundir con etiquetas humanas del título tipo `EP-26`, `RF-001`.
- **Gate determinista PURO:** función sin LLM/red/reloj/disco que, dado un input, siempre da el mismo veredicto. Patrón de referencia: `harness/epic_gate.py`.
- **FLAG_REGISTRY:** tupla en `services/harness_flags.py` que hace que un flag aparezca en la UI sin tocar el frontend.
- **Ratchet del arnés:** lista de tests (`scripts/run_harness_tests.ps1`) que se corren siempre para evitar regresiones.
- **Warning vs blocking:** warning = adjunta el veredicto y deja pasar; blocking = devuelve 400 y no crea la Task. Blocking es opt-in dentro de opt-in.

## 8. Orden de implementación
1. **F0** — flags + lectores + `test_task_gate_flags.py` (verde).
2. **F1** — `harness/task_gate.py` + `test_task_gate.py` (verde).
3. **F2** — wiring en `create_child_task` + `test_create_child_task_gate.py` (verde).
4. **F3** — veredicto en SystemLog + test de auditoría (verde).
5. **F4** — centinela de NO-regresión flag-OFF (verde, + suite existente sin regresión).
6. **F5** — ratchet en `run_harness_tests.ps1`.

## 9. Definición de Hecho (DoD global)
- [ ] Los 2 flags están en `FLAG_REGISTRY` (visibles en UI) y sus lectores existen, default OFF.
- [ ] `harness/task_gate.py` es PURO (sin disco/red/LLM/reloj), nunca lanza, determinista (sorted).
- [ ] Con ambos flags OFF, `create_child_task` es **byte-idéntico** al actual (test F4 verde; sin clave `task_gate`; sin import de `task_gate`).
- [ ] Con `STACKY_TASK_GATE_ENABLED=true`, la respuesta y el SystemLog incluyen `task_gate` con defects deterministas; NO bloquea.
- [ ] Con `STACKY_TASK_GATE_BLOCKING=true` + veredicto blocking, devuelve 400 `TASK_GATE_BLOCKED` y NO crea la Task (salvo dry_run).
- [ ] Todos los tests nombrados verdes con el venv del repo; los 3 archivos están en el ratchet.
- [ ] **[ADICIÓN ARQUITECTO]** `test_defect_vocabulary_is_frozen` implementado y verde (congela `_ALL_CODES`). *(Pendiente: lo único de v2 aún no construido.)*
- [ ] Paridad-3 trivial (backend); cero trabajo del operador; human-in-the-loop intacto; sin auth nueva; sin degradación.

---

### Resumen (5 líneas)
1. **Qué propone:** un gate determinista PURO (`harness/task_gate.py`, mirror de `epic_gate.py`) que valida el CONTENIDO del `pending-task.json` (hoy sólo se valida presencia de claves) y adjunta/bloquea un veredicto en `create_child_task`, cerrando la asimetría épica-vs-funcional.
2. **Valor/KPI:** protege el contrato de trabajo REAL del desarrollador (el flujo menos blindado, donde se concentra el dolor histórico) con defects deterministas; warning por default, blocking opt-in.
3. **Por qué NO agrega trabajo al operador:** flags default OFF (byte-idéntico), opt-in, visibles/activables desde la UI vía `FLAG_REGISTRY`; el operador no hace nada nuevo salvo, si quiere, encenderlo.
4. **3 runtimes:** paridad trivial — el gate corre en el endpoint backend que consume el archivo, sea cual sea el runtime que lo produjo; no hay rama ni fallback per-runtime.
5. **Es hardening, no game-changer:** reusa epic_gate/constantes/ratchet existentes, no inventa alcance, y no toca el flujo épica ya protegido.
