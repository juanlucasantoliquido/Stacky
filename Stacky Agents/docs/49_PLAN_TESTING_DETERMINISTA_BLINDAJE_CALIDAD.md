# 49 — PLAN: Testing Determinista y Blindaje de Calidad del Arnés

> Estado: IMPLEMENTADO 2026-06-19 · v2
>
> Evidencia: F0/F1/F2/F7 ya existían (evals/extraction_golden_runner.py + 12 fixtures + tests/test_golden_extraction.py + tests/test_extraction_detects_pathologies.py, 16 verdes). Implementado ahora: F3 (tests/conformance/test_runtime_conformance.py:57 ALL_RUNTIMES + test_github_copilot_exception_documented, 21 verdes), F4 (tests/test_harness_ratchet_meta.py + tests/harness_ratchet_allowlist.txt 194 entradas), F5 (tests/test_no_determinism_sentinel.py, _JUSTIFIED para time.monotonic/time.time de los runners), F6 (4 archivos en run_harness_tests.sh:57 y .ps1:49). Ratchet: PASS=35/36 (el único FAIL es test_u2_publish_review_mode.py por polución sqlite preexistente, no regresión). Los 4 archivos nuevos PASS.
> Para ser implementado por un modelo menor (Haiku / Codex / GitHub Copilot Pro) SIN inferir nada.
> Toda ruta, símbolo y comando de este plan fue verificado contra el repo en la fecha de redacción.

## v1 → v2 (CHANGELOG — tras crítica adversarial verificada contra el código)

Verificado contra `api/tickets.py`, `tests/conformance/test_runtime_conformance.py`,
`harness/capabilities.py`, `evals/golden_runner.py`, `scripts/run_harness_tests.sh` y `.ps1`.

- **C1 (BLOQUEANTE) — F2 inventaba semántica falsa de `ordinal_id_mismatch`.** El v1
  derivaba la patología "ordinal≠ADO-id" de `task_ado_id` no-int dentro del
  `pending-task.json`. FALSO: `task_ado_id` **NO** pertenece a
  `_PENDING_TASK_REQUIRED_FIELDS` (`tickets.py:40-44`); pertenece a
  `_CONSUMED_METADATA_KEYS` (`tickets.py:62-67`) y lo escribe **Stacky al consumir**
  (cuando ya creó la task en ADO, `tickets.py:1947`), NO el agente en el pending
  original. Cuando el agente escribe el pending, el ADO-id **todavía no existe** →
  no es testeable sobre el pending puro. F2 reescrita: se eliminó `ordinal_id_mismatch`
  y se reemplazó por validaciones de campos REALES del contrato (`status` canónico
  vs alias legacy, tipos de `epic_id`/`rf_id`). La patología "ordinal≠ADO-id" se
  reconoce explícitamente como NO-blindable en el pending puro y se mueve a Fuera de scope.
- **C2 (IMPORTANTE) — magnitud de la allowlist F4 mal estimada.** El v1 decía "~69
  archivos sin clasificar"; el repo tiene **220** `tests/test_*.py` y ~30 en el ratchet
  → allowlist semilla ≈ **190**. Corregida la cifra y reforzado R5.
- **C3 (IMPORTANTE) — F6 asumía formato idéntico .sh/.ps1.** El `.ps1` usa
  `$HarnessTestFiles = @( "tests/x.py", ... )` (comillas + comas), distinto del bash
  `( tests/x.py )`. F6 ahora da el snippet EXACTO para cada archivo por separado.
- **C4 (MENOR) — venv literal.** Todos los comandos ahora muestran cómo resolver el
  intérprete del venv (`stacky-backend-dev-test-env`: pin pywin32==306 roto en py3.13).
- **[ADICIÓN ARQUITECTO] F7 — Anti-blindaje: meta-test que valida que los extractores
  DETECTAN las patologías (no solo que el corpus existe).** Ver F7.

---

## 1. Título, objetivo y KPI

**Título:** Blindaje de calidad determinista del núcleo del arnés Stacky.

**Objetivo (1 frase):** Convertir la maquinaria de calidad del arnés (extracción cruda, paridad de runtimes, ratchet de cobertura, determinismo) de "validada a mano / parcial" a "auto-verificada por tests deterministas que arrancan rojos y se endurecen".

**KPI (binarios, medibles):**
- **K1:** Existe un golden-set determinista de extracción cruda con ≥ 8 fixtures sintéticos que cubre las patologías históricas BLINDABLES sobre función pura (épica narrada, HTML embebido en prosa, HTML duplicado, heading sin RF; y para pending-task: JSON roto, campos faltantes, `status` no-canónico), corriendo sin LLM ni reloj. `python -m pytest tests/test_golden_extraction.py -q` → verde. NOTA: la patología "ordinal≠ADO-id" NO es blindable en el pending-task puro (el ADO-id no existe cuando el agente escribe el pending) — ver §6 Fuera de scope.
- **K2:** La suite de conformance parametriza los **3** runtimes (`claude_code_cli`, `codex_cli`, `github_copilot`), con excepción explícita y documentada para `github_copilot` donde aplique. `python -m pytest tests/conformance/test_runtime_conformance.py -q` → verde.
- **K3:** Existe un meta-test que falla si un archivo `tests/test_*.py` nuevo no está ni en `HARNESS_TEST_FILES` ni en una allowlist explícita con motivo. `python -m pytest tests/test_harness_ratchet_meta.py -q` → verde.
- **K4:** Existe un centinela estático que prohíbe fuentes de no-determinismo (`datetime.now(`, `time.time(`, `random.`) dentro de un allowlist de módulos del núcleo del arnés, salvo seam inyectable o excepción justificada. `python -m pytest tests/test_no_determinism_sentinel.py -q` → verde.

**Definición de "verde":** exit code 0 del comando citado, sin `xfail` no marcado ni `skip` silencioso de los casos núcleo.

---

## 2. Por qué ahora / gap

Los planes 27–32 (motor invisible, lifecycle, calidad, grounding, verificación ejecutable, contrato de aceptación) verifican **el entregable** del agente: que la épica esté grounded, que el contrato de aceptación se cumpla, que el resultado compile. Pero **la maquinaria que produce y valida ese entregable** (los extractores puros sobre el output crudo, la paridad de los 3 runtimes, el ratchet de cobertura) no tiene su propia red de seguridad determinista:

- **Gap M1:** la regresión #1 histórica ("la épica/task nunca se crea en ADO") nace en los extractores `_extract_epic_html` / `_looks_like_epic` y en el parseo de `pending-task.json`. Hoy existen tests sueltos (`test_epic_html_extraction.py`, `test_epic_narration_guard.py`) pero NO un corpus congelado de outputs CRUDOS sintéticos (prosa+HTML, HTML duplicado, JSON roto, campos faltantes) con artefacto esperado, al estilo golden-set. El golden-set actual (`evals/golden_runner.py`) juzga el **contrato** (`contract_validator.validate`), no la **extracción**. **Aclaración v2:** la sub-patología "ordinal≠ADO-id" (memoria `functional-task-not-created-root-cause`) NO se origina en el `pending-task.json` puro — `task_ado_id` es metadata de CONSUMO que Stacky escribe DESPUÉS de crear la task (`_CONSUMED_METADATA_KEYS`, `tickets.py:62`), no un campo que el agente provea. Por eso M1 NO la cubre y se documenta como fuera de scope.
- **Gap M3:** `RUNNER_SOURCES` en `tests/conformance/test_runtime_conformance.py` solo cubre `claude_code_cli` y `codex_cli`. `github_copilot` está declarado en `harness/capabilities.py:CAPABILITIES` (con `writes_artifacts=True`) pero NO entra en la parametrización de conformance → su paridad no está verificada.
- **Gap M2:** el ratchet `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh`) es **manual**: nada impide que un test nuevo entre sin clasificar y la cobertura del arnés se encoja en silencio (riesgo D7 del plan 22).
- **Gap M4:** no hay centinela que impida reintroducir `datetime.now()` / `random` / orden no fijado en el núcleo del arnés, lo que rompería el determinismo que M1 depende.

Mejoras invisibles al operador, muy visibles en calidad: ninguna toca la UI ni el flujo del operador; todas son tests/CI.

---

## 3. Principios y guardarraíles (NO negociables)

- **G1 — 3 runtimes con paridad o degradación controlada:** todo check de conformance corre para los 3 runtimes; donde un runtime no soporte una capacidad, se declara excepción EXPLÍCITA leyendo `RuntimeCapabilities` (fallback documentado), nunca un skip mudo.
- **G2 — Cero trabajo extra al operador:** todo es test/CI. Cada fase declara `Trabajo del operador: ninguno`.
- **G3 — Human-in-the-loop intacto:** no se altera ningún flujo de aprobación; estos tests no publican, no llaman LLMs, no tocan ADO.
- **G4 — Mono-operador sin auth:** no se introduce RBAC ni dependencias de identidad.
- **G5 — No degradar perf/seguridad/estabilidad/DX; backward-compatible; reusar lo existente:** se reusa el shape JSON de `golden_runner.py`, la mecánica de introspección de `test_runtime_conformance.py` y el ratchet de `run_harness_tests.sh`. No se renombran símbolos públicos.
- **G6 — NO tratar datos personales:** todos los fixtures de M1 son **sintéticos/anonimizados** (RF inventados, IDs ficticios, sin nombres reales de clientes/personas). Prohibido copiar outputs reales de Pacífico u otro cliente.
- **G7 — Test-first obligatorio:** cada fase agrega primero el fixture/caso que HOY falla (rojo por la razón correcta) y recién después endurece.

### Decisión de diseño que NO se debe revertir (M1)

> El golden-set de M1 va sobre **EXTRACTORES PUROS** (`_extract_epic_html`, `_looks_like_epic`, y el validador de campos del `pending-task.json`), **NO sobre captura/replay de los CLIs**.
> Se **rechazó** capturar runs completos (cassettes/grabaciones de los 3 CLIs) por dos motivos: (a) riesgo de paridad entre los 3 runtimes — un cassette de un runtime no representa a los otros; (b) no-determinismo de los cassettes (timestamps, orden, tokens).
> **Razón de fondo:** el extractor es una **función pura sobre string** → determinismo total sin tocar CLIs, sin red, sin reloj y sin datos personales. Esto es lo que hace el golden-set blindable.

---

## 4. Fases

> Convenciones de comando: el repo corre tests **por archivo** con el python del venv (ver memoria `stacky-backend-dev-test-env`). Working dir de todos los comandos: `Stacky Agents/backend`. Si el venv tiene un python propio, sustituir `python` por la ruta a ese intérprete; el ratchet (`run_harness_tests.sh`) usa `PYTHON` como variable de entorno.

---

### F0 — Andamiaje del golden-set de extracción (test-first, arranca rojo)

**Objetivo:** crear el directorio de fixtures y el runner análogo a `golden_runner.py` pero para extractores puros, con UN fixture que hoy falle. **Valor:** establece la infraestructura determinista reusable; prueba que el rojo aparece por la razón correcta.

**Archivos exactos a crear:**
- `Stacky Agents/backend/evals/extraction_golden_runner.py` (runner nuevo, hermano de `evals/golden_runner.py`).
- `Stacky Agents/backend/evals/extraction_fixtures/` (carpeta de fixtures JSON).
- `Stacky Agents/backend/evals/extraction_fixtures/epic_narrated_prose.json` (primer fixture, sintético).
- `Stacky Agents/backend/tests/test_golden_extraction.py` (test que corre el runner).

**Símbolos exactos reusados (verificados):**
- Extractores a invocar (en `backend/api/tickets.py`): `_extract_epic_html(raw: str | None) -> str` (línea 5406) y `_looks_like_epic(html: str | None) -> bool` (línea 5439). Son funciones módulo-privadas; el runner las importa con `from api.tickets import _extract_epic_html, _looks_like_epic`.
- Shape JSON: idéntico patrón al de `golden_runner.py` (campos `name`, `output`, `expect`).

**Shape del fixture JSON (contrato fijo para M1):**
```json
{
  "name": "epic_narrated_prose",
  "kind": "epic",
  "raw": "Voy a leer el archivo... La epica para EP-31 ya existe en disco. Listo.",
  "expect": {
    "extracted_html_contains": [],
    "looks_like_epic": false
  }
}
```
- `kind`: `"epic"` (usa `_extract_epic_html` + `_looks_like_epic`) o `"pending_task"` (usa el validador de campos de F2).
- `raw`: el output CRUDO sintético del agente (string).
- `expect.extracted_html_contains`: lista de substrings que DEBEN aparecer en `_extract_epic_html(raw)`.
- `expect.extracted_html_excludes`: (opcional) lista de substrings que NO deben aparecer (p. ej. narración).
- `expect.looks_like_epic`: bool esperado de `_looks_like_epic(_extract_epic_html(raw))`.

**Pseudocódigo del runner (`extraction_golden_runner.py`):**
```python
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from api.tickets import _extract_epic_html, _looks_like_epic

_FIXTURES_DIR = Path(__file__).resolve().parent / "extraction_fixtures"

@dataclass
class ExtractionCase:
    name: str
    kind: str
    raw: str
    expect: dict
    source: Path

def load_cases() -> list[ExtractionCase]:
    if not _FIXTURES_DIR.exists():
        return []
    cases = []
    for fx in sorted(_FIXTURES_DIR.glob("*.json")):
        d = json.loads(fx.read_text(encoding="utf-8"))
        cases.append(ExtractionCase(d["name"], d.get("kind", "epic"),
                                    d["raw"], d.get("expect", {}), fx))
    return cases

def evaluate(case: ExtractionCase) -> list[str]:
    """Devuelve lista de razones de fallo; vacía == OK."""
    reasons = []
    if case.kind == "epic":
        html = _extract_epic_html(case.raw)
        for sub in case.expect.get("extracted_html_contains", []):
            if sub not in html:
                reasons.append(f"falta substring {sub!r} en HTML extraido")
        for sub in case.expect.get("extracted_html_excludes", []):
            if sub in html:
                reasons.append(f"substring prohibido {sub!r} presente")
        exp = case.expect.get("looks_like_epic")
        if exp is not None and _looks_like_epic(html) != exp:
            reasons.append(f"looks_like_epic={_looks_like_epic(html)}, esperado {exp}")
    elif case.kind == "pending_task":
        reasons.extend(_evaluate_pending_task(case))  # definido en F2
    else:
        reasons.append(f"kind desconocido: {case.kind}")
    return reasons
```

**Test exacto (`tests/test_golden_extraction.py`):**
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/
import pytest
from evals.extraction_golden_runner import load_cases, evaluate

@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.name)
def test_extraction_golden(case):
    reasons = evaluate(case)
    assert not reasons, f"{case.name}: " + "; ".join(reasons)

def test_corpus_no_vacio():
    assert load_cases(), "el corpus de extraccion no puede estar vacio"
```

**Caso borde cubierto en F0:** el fixture `epic_narrated_prose` (narración sin tags) debe dar `looks_like_epic=false`. Verificar que HOY pasa o falla según el extractor — si el extractor ya lo maneja bien, marcar este fixture como el "ancla verde" y agregar en F1 un fixture que SÍ falle hoy.

**Comando de test (rojo→verde):**
```bash
cd "Stacky Agents/backend" && python -m pytest tests/test_golden_extraction.py -q
```

**Criterio de aceptación binario:** el comando corre, recoge ≥ 1 caso, y `test_corpus_no_vacio` pasa. (En F0 se admite que algún fixture intencionalmente-rojo falle: ese es el TDD.)

**Flag/protección:** ninguno (test, default = se corre siempre en CI y en el ratchet tras F2.allowlist).

**Impacto por runtime + fallback:** N/A — extractor puro sobre string, agnóstico de runtime. Los 3 runtimes producen outputs crudos que pasan por el mismo extractor; por eso el golden-set los cubre a todos sin distinción.

**Trabajo del operador: ninguno.**

---

### F1 — Corpus congelado: las 4 patologías de épica/HTML (test-first)

**Objetivo:** agregar fixtures sintéticos que cubren las patologías de extracción de épica/HTML, incluyendo ≥ 1 que HOY falle. **Valor:** blinda la regresión #1 (épica que nunca llega a ADO por narración o HTML sucio).

**Archivos exactos a crear (en `Stacky Agents/backend/evals/extraction_fixtures/`):**
- `epic_html_in_prose.json` — preámbulo en prosa + ```html ...``` + resumen final con emojis; `expect.extracted_html_contains` = `["<h1", "RF-"]`, `extracted_html_excludes` = `["Voy a", "Listo"]`, `looks_like_epic=true`.
- `epic_duplicated_blocks.json` — dos bloques ```html``` idénticos (el CLI a veces los repite); espera que `_extract_epic_html` devuelva UN solo bloque (`extracted_html_contains=["RF-001"]`).
- `epic_narration_only.json` — narración pura sin tags HTML; `looks_like_epic=false`, `extracted_html_excludes=["<h1"]`.
- `epic_heading_without_rf.json` — `<h1>` presente pero SIN bloque `<h2>RF-XXX`; `looks_like_epic=false` (este es el caso que ejercita la condición `has_rf_block` de `_looks_like_epic`).
- `epic_clean_no_fences.json` — HTML ya limpio sin fences (compat hacia atrás); `looks_like_epic=true`, `extracted_html_contains=["<h2"]`.

**Contenido sintético (ejemplo de `epic_html_in_prose.json`, todo ficticio):**
```json
{
  "name": "epic_html_in_prose",
  "kind": "epic",
  "raw": "Voy a leer el archivo de entrada.\n\n```html\n<h1>Epica: Carga de procesos batch</h1>\n<h2>RF-001 — Validar entrada</h2><p>El sistema valida el formato.</p>\n```\n\nListo, escribi la epica en disco.",
  "expect": {
    "extracted_html_contains": ["<h1>Epica", "RF-001"],
    "extracted_html_excludes": ["Voy a leer", "Listo, escribi"],
    "looks_like_epic": true
  }
}
```

**Casos borde explícitos:**
- Fence con tag en mayúsculas (` ```HTML `) — el regex de `_extract_epic_html` es case-insensitive; agregar variante en `epic_html_in_prose.json` o un fixture extra `epic_html_uppercase_fence.json`.
- `raw` vacío y `raw=null` — fixture `epic_empty.json` con `raw: ""` → `extracted_html=""`, `looks_like_epic=false`.

**Test:** el mismo `tests/test_golden_extraction.py` (parametrizado) recoge automáticamente los nuevos fixtures. No se edita el test.

**Comando:**
```bash
cd "Stacky Agents/backend" && python -m pytest tests/test_golden_extraction.py -q
```

**Procedimiento TDD obligatorio:** crear primero el fixture que se SOSPECHA falla (p. ej. `epic_duplicated_blocks` si la dedup no está garantizada), correr el comando, confirmar rojo con el mensaje correcto. Si el extractor ya lo maneja → el fixture queda como regresión-verde (igual valioso). Si falla → NO tocar el extractor en este plan salvo bug evidente; documentar el rojo como hallazgo y dejar el fixture marcado `expect` según comportamiento CORRECTO esperado (será el contrato que un fix posterior debe cumplir). Si el rojo es un bug real y trivial en el extractor, corregirlo con el cambio mínimo y re-correr.

**Criterio de aceptación binario:** `tests/test_golden_extraction.py` recoge ≥ 7 casos `kind=epic` y todos verdes (tras resolver los rojos legítimos con el cambio mínimo o ajustar `expect` al comportamiento correcto verificado).

**Flag/protección:** ninguno (test).

**Impacto por runtime + fallback:** N/A — extractor puro, cubre los 3 runtimes por construcción.

**Trabajo del operador: ninguno.**

---

### F2 — Corpus congelado: pending-task.json (JSON roto, campos faltantes, status no-canónico)

**Objetivo:** extender el golden-set al validador de campos del `pending-task.json`, cubriendo SOLO patologías blindables sobre la parte pura: JSON inválido, campos obligatorios faltantes y `status` no-canónico. **Valor:** blinda la regresión "crea archivos pero no la task" (ver memoria `functional-task-not-created-root-cause`) en su dimensión testeable sin filesystem ni ADO.

> **Corrección v2 (C1 — BLOQUEANTE resuelto):** el v1 incluía `ordinal_id_mismatch` derivado de `task_ado_id` no-int. ESO ES FALSO. Verificado: `task_ado_id` **NO** está en `_PENDING_TASK_REQUIRED_FIELDS` (`tickets.py:40-44` = `{generated_at, generated_by, epic_id, rf_id, title, description_html, plan_de_pruebas_path, parent_link_type, status}`). `task_ado_id` está en `_CONSUMED_METADATA_KEYS` (`tickets.py:62-67`) y lo escribe Stacky al CONSUMIR (`tickets.py:1947`, ya es int como `172`). Cuando el agente escribe el pending, el ADO-id todavía no existe. La patología "ordinal≠ADO-id" NO es blindable aquí → eliminada de F2, documentada en §6.

**Hecho verificado / restricción de diseño:** `_scan_pending_tasks_for_epic(repo_root, ado_id)` (`tickets.py:2167`) **NO es puro** (lee filesystem). NO se usa directamente. La parte PURA y determinista es:
1. El parseo `json.loads(text)` y su fallo (patología "JSON roto").
2. Campos obligatorios faltantes contra `_PENDING_TASK_REQUIRED_FIELDS` (`tickets.py:40`, `set` constante; mismo cómputo que `tickets.py:3646` `sorted(_PENDING_TASK_REQUIRED_FIELDS - set(payload.keys()))`).
3. `status` no-canónico: el valor canónico es `PENDING_TASK_STATUS_CANONICAL` (`tickets.py:51` = `"pending_manual_creation"`); `"pending"` es alias legacy aceptado. Cualquier otro valor es patológico.

**Símbolos exactos reusados:** `from api.tickets import _PENDING_TASK_REQUIRED_FIELDS, PENDING_TASK_STATUS_CANONICAL`.

**Archivo nuevo:** función pura `_validate_pending_task_payload(raw)` agregada **dentro de** `Stacky Agents/backend/evals/extraction_golden_runner.py` (NO en tickets.py; reusa solo constantes). Pseudocódigo:
```python
import json
from api.tickets import _PENDING_TASK_REQUIRED_FIELDS, PENDING_TASK_STATUS_CANONICAL

_STATUS_OK = {PENDING_TASK_STATUS_CANONICAL, "pending"}  # canonico + alias legacy

def _validate_pending_task_payload(raw: str | None) -> dict:
    """Pura: parsea el raw y reporta patologias. Nunca lanza."""
    out = {"json_ok": False, "missing_fields": sorted(_PENDING_TASK_REQUIRED_FIELDS),
           "status_canonical": False}
    if not raw:
        return out
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return out  # json_ok=False, missing_fields=todos
    out["json_ok"] = True
    if not isinstance(payload, dict):
        return out
    out["missing_fields"] = sorted(_PENDING_TASK_REQUIRED_FIELDS - set(payload.keys()))
    out["status_canonical"] = payload.get("status") in _STATUS_OK
    return out

def _evaluate_pending_task(case) -> list[str]:
    res = _validate_pending_task_payload(case.raw)
    reasons = []
    exp = case.expect
    if "json_ok" in exp and res["json_ok"] != exp["json_ok"]:
        reasons.append(f"json_ok={res['json_ok']}, esperado {exp['json_ok']}")
    if "missing_fields" in exp and sorted(res["missing_fields"]) != sorted(exp["missing_fields"]):
        reasons.append(f"missing_fields={res['missing_fields']}, esperado {exp['missing_fields']}")
    if "status_canonical" in exp and res["status_canonical"] != exp["status_canonical"]:
        reasons.append(f"status_canonical={res['status_canonical']}, esperado {exp['status_canonical']}")
    return reasons
```

**Fixtures a crear (en `extraction_fixtures/`, `kind="pending_task"`):**
- `pt_valid.json` — JSON válido con TODOS los campos de `_PENDING_TASK_REQUIRED_FIELDS` y `status:"pending_manual_creation"`; `expect`: `{json_ok:true, missing_fields:[], status_canonical:true}`.
- `pt_broken_json.json` — `raw` = string que NO parsea (`"{ rf_id: 12,"`); `expect`: `{json_ok:false}`.
- `pt_missing_fields.json` — JSON válido al que le faltan `parent_link_type` y `status`; `expect`: `{json_ok:true, missing_fields:["parent_link_type","status"]}`.
- `pt_status_no_canonico.json` — JSON válido completo pero `status:"done"` (no canónico ni alias); `expect`: `{json_ok:true, status_canonical:false}`.

**Contenido sintético de `pt_status_no_canonico.json` (todo ficticio, IDs en rango 900000+):**
```json
{
  "name": "pt_status_no_canonico",
  "kind": "pending_task",
  "raw": "{\"generated_at\":\"2026-01-01T00:00:00Z\",\"generated_by\":\"functional-agent\",\"epic_id\":900001,\"rf_id\":\"RF-001\",\"title\":\"Tarea sintetica\",\"description_html\":\"<p>x</p>\",\"plan_de_pruebas_path\":\"p.md\",\"parent_link_type\":\"child\",\"status\":\"done\"}",
  "expect": { "json_ok": true, "status_canonical": false }
}
```

**Test:** mismo `tests/test_golden_extraction.py` (recoge `kind=pending_task` vía `evaluate`).

**Comando (con resolución de venv — C4):**
```bash
cd "Stacky Agents/backend"
# Usar el python del venv si existe; si no, el global. Verificar SIEMPRE primero:
PYBIN="$(ls .venv/Scripts/python.exe 2>/dev/null || ls .venv/bin/python 2>/dev/null || command -v python)"
"$PYBIN" -m pytest tests/test_golden_extraction.py -q
```

**Procedimiento TDD:** crear primero `pt_broken_json.json` y `pt_status_no_canonico.json` (rojos esperados antes de implementar `_validate_pending_task_payload`), confirmar `ImportError`/lógica faltante, implementar la función pura, confirmar verde.

**Criterio de aceptación binario:** `tests/test_golden_extraction.py` recoge ≥ 4 casos `kind=pending_task` y todos verdes; total del corpus ≥ 8 fixtures (K1).

**Flag/protección:** ninguno (test).

**Impacto por runtime + fallback:** N/A — validación pura sobre el contenido del archivo; el `pending-task.json` lo escribe el agente funcional en cualquiera de los 3 runtimes con `writes_artifacts=True`.

**Trabajo del operador: ninguno.**

---

### F3 — Paridad de los 3 runtimes en conformance (M3)

**Objetivo:** incluir `github_copilot` en la suite de conformance, declarando excepción explícita donde no tenga runner CLI dedicado. **Valor:** garantiza que ningún runtime quede sin verificación de cableado/capacidades.

**Hechos verificados:**
- `RUNNER_SOURCES` (`tests/conformance/test_runtime_conformance.py:37`) hoy solo mapea `claude_code_cli` → `services/claude_code_cli_runner.py` y `codex_cli` → `services/codex_cli_runner.py`.
- `github_copilot` **NO tiene runner CLI dedicado**: su flujo es el estándar en `backend/agent_runner.py` (no hay `services/*copilot*runner.py`). Por eso NO puede entrar en los tests que hacen `_source(runtime)` (lectura del archivo del runner) sin un archivo destino.
- `github_copilot` SÍ está en `harness/capabilities.py:CAPABILITIES` con: `writes_artifacts=True`, `supports_stdin_feedback=False`, `supports_resume=False`, `supports_mcp=False`, `has_stream_telemetry=False`.

**Diseño de la solución (degradación controlada, G1):**
Separar los tests en dos grupos por su naturaleza:
1. **Tests de CAPACIDADES** (no leen el runner; consultan `CAPABILITIES`): deben parametrizar los **3** runtimes. Hoy `test_runtime_declared_in_capabilities` usa `CLI_RUNTIMES` (solo 2); pasarlo a la lista de los 3.
2. **Tests de CABLEADO de runner CLI** (hacen `_source(runtime)` y buscan tokens como `post_run`, `RunawayGuard`, etc.): siguen sobre `CLI_RUNTIMES` (los 2 con runner propio). `github_copilot` queda EXCLUIDO con motivo documentado: no tiene runner CLI; su cableado de post-run/telemetría vive en el path estándar de `agent_runner.py` y se cubre por otros tests.

**Cambios exactos en `tests/conformance/test_runtime_conformance.py`:**
```python
# Antes:
CLI_RUNTIMES = sorted(RUNNER_SOURCES)

# Despues (agregar lista de TODOS los runtimes declarados):
ALL_RUNTIMES = sorted(_capabilities())          # incluye github_copilot
CLI_RUNTIMES = sorted(RUNNER_SOURCES)           # solo los que tienen runner CLI propio
```
- Cambiar **solo** `test_runtime_declared_in_capabilities` para parametrizar sobre `ALL_RUNTIMES` (verifica que los 3 estén en `CAPABILITIES` con flags bool). Los demás tests parametrizados (`post_run`, `telemetry`, `runaway_guard`, `failure_taxonomy`, `repro_script`, `canonical_metadata_keys`, `resume`) **mantienen** `CLI_RUNTIMES`.
- Agregar un test NUEVO de excepción documentada:
```python
def test_github_copilot_exception_documented():
    """github_copilot no tiene runner CLI dedicado (flujo estandar en
    agent_runner.py). Su exclusion de los tests de cableado CLI es deliberada,
    no un olvido. Este test fija esa decision: si alguien agrega un runner CLI
    de copilot, debe sumarlo a RUNNER_SOURCES y este assert lo recordara."""
    assert "github_copilot" in _capabilities()
    assert "github_copilot" not in RUNNER_SOURCES, (
        "Si github_copilot gana runner CLI propio, agregalo a RUNNER_SOURCES "
        "y conectalo a los seams del arnes (post_run, telemetry, RunawayGuard)."
    )
    cap = _capabilities()["github_copilot"]
    # Capacidades esperadas del path estandar (fallback documentado):
    assert cap.writes_artifacts is True
    assert cap.supports_resume is False
    assert cap.supports_mcp is False
```

**Test:** el propio `tests/conformance/test_runtime_conformance.py`.

**Comando:**
```bash
cd "Stacky Agents/backend" && python -m pytest tests/conformance/test_runtime_conformance.py -q
```

**Procedimiento TDD:** primero parametrizar `test_runtime_declared_in_capabilities` sobre `ALL_RUNTIMES` SIN el test de excepción → confirmar que sigue verde (github_copilot ya está en CAPABILITIES, así que este test pasará; el rojo real sería si alguien removiera github_copilot de CAPABILITIES). Luego agregar `test_github_copilot_exception_documented`. Si en el futuro alguien intentara colar github_copilot en `RUNNER_SOURCES` sin runner, este test se vuelve rojo → eso es el guard.

**Criterio de aceptación binario:** la suite recoge `test_runtime_declared_in_capabilities[github_copilot]` y `test_github_copilot_exception_documented`, ambos verdes; los tests de cableado siguen corriendo para `claude_code_cli` y `codex_cli`.

**Flag/protección:** ninguno (test).

**Impacto por runtime + fallback:**
- `claude_code_cli` / `codex_cli`: sin cambios — siguen bajo todos los checks de cableado.
- `github_copilot`: entra al check de capacidades; excluido de checks de cableado CLI con **fallback explícito documentado** (path estándar `agent_runner.py`, `writes_artifacts=True`). Si gana runner CLI, el test de excepción fuerza a re-cablearlo.

**Trabajo del operador: ninguno.**

---

### F4 — Meta-test de ratchet de cobertura (M2)

**Objetivo:** un meta-test que falla si un `tests/test_*.py` no está en `HARNESS_TEST_FILES` ni en una allowlist explícita. **Valor:** convierte el ratchet de manual a auto-verificado; impide que la cobertura del arnés se encoja en silencio.

**Hechos verificados:**
- Ratchet en `Stacky Agents/backend/scripts/run_harness_tests.sh`, variable bash `HARNESS_TEST_FILES=( ... )` (línea 20), entradas tipo `tests/test_harness_flags.py`. Existe también `run_harness_tests.ps1` (no se parsea; fuente de verdad = `.sh`).
- El triage de los archivos de `tests/` no clasificados **NO es parte del DoD** de este plan (trabajo de seguimiento). **Magnitud real verificada (v2, C2):** hay **220** archivos `tests/test_*.py` y ~30 en `HARNESS_TEST_FILES` → la allowlist semilla tendrá **≈ 190** entradas. Este plan entrega el meta-test + una **allowlist semilla** auto-generada (no se escribe a mano).

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_harness_ratchet_meta.py` (el meta-test).
- `Stacky Agents/backend/tests/harness_ratchet_allowlist.txt` (allowlist semilla: archivos `tests/test_*.py` deliberadamente fuera del arnés, uno por línea, con `# motivo` al lado).

**Lógica del meta-test (pseudocódigo):**
```python
import re, pathlib, pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]   # backend/
_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"
_ALLOWLIST = _BACKEND / "tests" / "harness_ratchet_allowlist.txt"
_TESTS_DIR = _BACKEND / "tests"

def _ratchet_files() -> set[str]:
    """Parsea HARNESS_TEST_FILES del .sh: lineas que empiezan con 'tests/'."""
    text = _SCRIPT.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*(tests/[\w/]+\.py)\s*$", text, re.MULTILINE))

def _allowlist() -> set[str]:
    if not _ALLOWLIST.exists():
        return set()
    out = set()
    for line in _ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out

def _all_test_files() -> set[str]:
    """Todos los tests/test_*.py relativos a backend/, posix-normalizados."""
    return {
        p.relative_to(_BACKEND).as_posix()
        for p in _TESTS_DIR.rglob("test_*.py")
    }

def test_ratchet_clasifica_todos_los_tests():
    ratchet = _ratchet_files()
    allow = _allowlist()
    todos = _all_test_files()
    sin_clasificar = sorted(todos - ratchet - allow)
    assert not sin_clasificar, (
        "Tests no clasificados (agregalos a HARNESS_TEST_FILES en "
        "scripts/run_harness_tests.sh si pasan aislados, o a "
        "tests/harness_ratchet_allowlist.txt con motivo):\n  - "
        + "\n  - ".join(sin_clasificar)
    )

def test_allowlist_no_se_solapa_con_ratchet():
    overlap = _ratchet_files() & _allowlist()
    assert not overlap, f"Archivos en ratchet Y allowlist (redundante): {sorted(overlap)}"

def test_ratchet_no_referencia_archivos_inexistentes():
    faltantes = sorted(f for f in _ratchet_files() if not (_BACKEND / f).exists())
    assert not faltantes, f"HARNESS_TEST_FILES referencia archivos inexistentes: {faltantes}"
```

**Allowlist semilla (`harness_ratchet_allowlist.txt`):** dado que el triage NO es del DoD, la semilla debe contener TODOS los `tests/test_*.py` que HOY no están en `HARNESS_TEST_FILES` (≈190 entradas), cada uno con motivo `# pendiente-de-triage`. Procedimiento determinista para generarla:
```bash
cd "Stacky Agents/backend"
# 1. Listar todos los tests:
python - <<'PY'
import re, pathlib
backend = pathlib.Path(".").resolve()
script = (backend/"scripts"/"run_harness_tests.sh").read_text(encoding="utf-8")
ratchet = set(re.findall(r"^\s*(tests/[\w/]+\.py)\s*$", script, re.MULTILINE))
todos = {p.relative_to(backend).as_posix() for p in (backend/"tests").rglob("test_*.py")}
faltan = sorted(todos - ratchet)
with open("tests/harness_ratchet_allowlist.txt","w",encoding="utf-8") as f:
    f.write("# Allowlist semilla del ratchet (plan 49 F4).\n")
    f.write("# Cada archivo aqui esta deliberadamente FUERA de HARNESS_TEST_FILES.\n")
    f.write("# Triage (mover al ratchet los que pasen aislados) = trabajo de seguimiento.\n")
    for x in faltan:
        f.write(f"{x}  # pendiente-de-triage\n")
print(f"{len(faltan)} archivos en allowlist semilla")
PY
```
> Importante: este script genera el archivo PERO el meta-test es lo que se versiona como guard. La allowlist crece o decrece a mano cuando se haga el triage real.

**Test (este mismo archivo):**
```bash
cd "Stacky Agents/backend" && python -m pytest tests/test_harness_ratchet_meta.py -q
```

**Procedimiento TDD:** escribir el meta-test PRIMERO con la allowlist vacía → rojo (lista ~69 archivos sin clasificar). Generar la allowlist semilla con el script de arriba → verde. Confirmar que crear un `tests/test_zz_dummy.py` nuevo (temporal) vuelve a poner el meta-test en rojo, y borrarlo.

**Criterio de aceptación binario:** `tests/test_harness_ratchet_meta.py` verde con la allowlist semilla presente; un test nuevo no clasificado lo pone en rojo (verificado manualmente con un dummy temporal y luego borrado).

**Flag/protección:** ninguno (meta-test, default = corre siempre). **Este meta-test DEBE agregarse a `HARNESS_TEST_FILES`** (se auto-incluye en el ratchet).

**Impacto por runtime + fallback:** N/A — estático sobre el árbol de tests, agnóstico de runtime.

**Trabajo del operador: ninguno.**

---

### F5 — Centinela de no-determinismo acotado (M4)

**Objetivo:** meta-test estático que prohíbe `datetime.now(`, `time.time(`, `random.` y orden no fijado en un allowlist de módulos del núcleo del arnés. **Valor:** protege el determinismo del que dependen M1 y todo el arnés; impide reintroducir fuentes de no-determinismo.

**Hechos verificados — módulos del núcleo (rutas reales):**
- `backend/contract_validator.py`
- `backend/harness/` → `capabilities.py`, `complexity.py`, `criteria_repair.py`, `exec_repair.py`, `failure.py`, `model_policy.py`, `post_run.py`, `pricing.py`, `resume.py`, `run_contract.py`, `run_repair.py`, `runaway_guard.py`, `telemetry.py`
- Runners CLI: `backend/services/claude_code_cli_runner.py`, `backend/services/codex_cli_runner.py`

**Diseño (no global, para no ser ruidoso — G5):** allowlist EXPLÍCITA de archivos. Patrones prohibidos como literales de texto sobre el source (grep, no ejecución):
- `datetime.now(` (sin `tz`/seam) — relojes
- `time.time(` — relojes
- `random.` — aleatoriedad (excepto `import random` no usado, pero el patrón `random.` cubre llamadas)
- `time.monotonic(` — relojes (incluir)

**Excepciones permitidas (seam inyectable):** si un módulo necesita tiempo, debe recibirlo por parámetro/inyección (p. ej. `now: datetime | None = None`) y NO llamar al reloj directo en la ruta pura. Donde sea legítimo e inevitable, se agrega el archivo+patrón a una sub-allowlist con motivo.

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_no_determinism_sentinel.py`

**Lógica (pseudocódigo):**
```python
import re, pathlib, pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

# Modulos del nucleo del arnes vigilados (rutas relativas a backend/).
_GUARDED = [
    "contract_validator.py",
    "harness/capabilities.py", "harness/complexity.py", "harness/criteria_repair.py",
    "harness/exec_repair.py", "harness/failure.py", "harness/model_policy.py",
    "harness/post_run.py", "harness/pricing.py", "harness/resume.py",
    "harness/run_contract.py", "harness/run_repair.py", "harness/runaway_guard.py",
    "harness/telemetry.py",
    "services/claude_code_cli_runner.py", "services/codex_cli_runner.py",
]

_FORBIDDEN = [
    re.compile(r"\bdatetime\.now\("),
    re.compile(r"\btime\.time\("),
    re.compile(r"\btime\.monotonic\("),
    re.compile(r"\brandom\.\w"),
]

# (archivo, patron_str) explicitamente justificados. Vacio al inicio.
_JUSTIFIED = {
    # ("services/codex_cli_runner.py", r"\btime\.monotonic\("): "timeout real del subproceso, no afecta output",
}

@pytest.mark.parametrize("rel", _GUARDED, ids=lambda r: r)
def test_no_fuentes_de_no_determinismo(rel):
    path = _BACKEND / rel
    assert path.exists(), f"modulo vigilado inexistente: {rel} (actualizar _GUARDED)"
    src = path.read_text(encoding="utf-8")
    hits = []
    for pat in _FORBIDDEN:
        if pat.search(src) and (rel, pat.pattern) not in _JUSTIFIED:
            hits.append(pat.pattern)
    assert not hits, (
        f"{rel}: fuente(s) de no-determinismo {hits}. "
        "Refactorizar a seam inyectable (recibir now/rng por parametro) "
        "o agregar a _JUSTIFIED con motivo."
    )
```

**Caso borde:** comentarios o docstrings que mencionen `datetime.now(` darían falso positivo. Mitigación: si aparece un falso positivo en un comentario, agregar a `_JUSTIFIED` con motivo `# solo en comentario`. (Análisis AST sería más preciso pero se descarta por costo/complejidad; grep es suficiente para un allowlist chico — ver Fuera de scope.)

**Test:**
```bash
cd "Stacky Agents/backend" && python -m pytest tests/test_no_determinism_sentinel.py -q
```

**Procedimiento TDD:** correr el centinela tal cual → puede arrancar ROJO si algún módulo del núcleo ya usa `datetime.now()`/`time.*`. Para cada rojo: (a) si es ruta pura → refactor a seam inyectable con el cambio mínimo; (b) si es inevitable y no afecta el output (p. ej. medir timeout de subproceso) → agregar a `_JUSTIFIED` con motivo. NO ampliar `_GUARDED` más allá del núcleo en este plan.

**Criterio de aceptación binario:** `tests/test_no_determinism_sentinel.py` verde con `_GUARDED` cubriendo los 16 módulos listados; cada entrada en `_JUSTIFIED` tiene motivo escrito.

**Flag/protección:** ninguno (meta-test, default = corre siempre). **Agregar a `HARNESS_TEST_FILES`.**

**Impacto por runtime + fallback:** vigila los runners de `claude_code_cli` y `codex_cli` (los que tienen archivo propio). `github_copilot` no tiene runner CLI → su determinismo se cubre indirectamente vía los módulos `harness/*` compartidos que sí están vigilados. Fallback documentado: si copilot gana runner, sumarlo a `_GUARDED`.

**Trabajo del operador: ninguno.**

---

### F6 — Integración en el ratchet y cierre

**Objetivo:** registrar los tests nuevos en el ratchet curado para que corran siempre. **Valor:** los blindajes nuevos quedan en la red de seguridad permanente del arnés.

**Cambios exactos en `Stacky Agents/backend/scripts/run_harness_tests.sh`** — agregar dentro de `HARNESS_TEST_FILES=( ... )`, sección nueva al final del array (antes del cierre `)` de la línea 57). Formato bash (SIN comillas, SIN comas):
```bash
  # — Plan 49 · Blindaje de calidad determinista —
  tests/test_golden_extraction.py
  tests/test_harness_ratchet_meta.py
  tests/test_no_determinism_sentinel.py
  tests/test_extraction_detects_pathologies.py
```

**Cambios exactos en `Stacky Agents/backend/scripts/run_harness_tests.ps1`** (C3 — formato DISTINTO: `$HarnessTestFiles = @( ... )`, CON comillas dobles y comas; agregar antes del cierre `)`):
```powershell
  # — Plan 49 · Blindaje de calidad determinista —
  "tests/test_golden_extraction.py",
  "tests/test_harness_ratchet_meta.py",
  "tests/test_no_determinism_sentinel.py",
  "tests/test_extraction_detects_pathologies.py"
```
> `tests/conformance/test_runtime_conformance.py` YA está en el ratchet (`.sh` línea 56) — no duplicar.
> OJO: la última entrada del array `.ps1` NO lleva coma final si queda como último elemento; si se agrega después de un elemento existente, poner coma al elemento previo. Verificar el cierre con `python -m pytest tests/test_harness_ratchet_meta.py -q` (el meta-test de F4 valida que todo lo referenciado exista).

**Test de cierre (corre todo el ratchet por archivo):**
```bash
cd "Stacky Agents/backend" && bash scripts/run_harness_tests.sh
```

**Criterio de aceptación binario:** `bash scripts/run_harness_tests.sh` imprime `FAIL=0  MISSING=0` y exit 0; los 3 archivos nuevos aparecen como `PASS`.

**Flag/protección:** ninguno.

**Impacto por runtime + fallback:** N/A.

**Trabajo del operador: ninguno.**

---

### F7 — [ADICIÓN ARQUITECTO] Meta-test anti-blindaje: los extractores DETECTAN, no solo existen

**Problema que resuelve (gap que el v1 no veía):** un golden-set puede dar "verde" por dos razones opuestas — porque el extractor funciona, o porque el extractor está roto Y el fixture `expect` también está mal/laxo (R1). Peor: si alguien neutraliza un extractor (p. ej. `_looks_like_epic` que siempre devuelve `True`), los fixtures de "happy path" siguen verdes y la regresión #1 vuelve sin que nada se ponga rojo. El corpus blinda contra cambios en el INPUT, no contra la degradación del extractor mismo.

**Objetivo:** un meta-test que prueba la **propiedad discriminante** de los extractores: que existe AL MENOS un fixture donde el extractor dice "esto NO es épica / esto está mal" y AL MENOS uno donde dice "esto SÍ es épica / está bien". Si un extractor pierde su capacidad de discriminar (siempre `True` o siempre `False`), este test se vuelve rojo aunque cada fixture individual pase.

**Archivo a crear:** `Stacky Agents/backend/tests/test_extraction_detects_pathologies.py`

**Lógica (pseudocódigo, reusa el runner de F0):**
```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from evals.extraction_golden_runner import load_cases

def _epic_cases():
    return [c for c in load_cases() if c.kind == "epic"
            and "looks_like_epic" in c.expect]

def test_looks_like_epic_discrimina_ambos_polos():
    """El corpus DEBE contener al menos un caso esperado-True y uno
    esperado-False para looks_like_epic. Sin ambos polos, un extractor
    constante (siempre True / siempre False) pasaria sin detectarse."""
    polos = {c.expect["looks_like_epic"] for c in _epic_cases()}
    assert True in polos, "falta fixture epic con looks_like_epic=True"
    assert False in polos, "falta fixture epic con looks_like_epic=False (anti-narracion)"

def test_pending_task_cubre_json_roto_y_valido():
    pt = [c for c in load_cases() if c.kind == "pending_task" and "json_ok" in c.expect]
    polos = {c.expect["json_ok"] for c in pt}
    assert True in polos and False in polos, (
        "el corpus pending_task debe cubrir JSON valido (true) y roto (false)")
```

**Por qué es de alto valor y barato:** cero tokens de runtime, cero LLM, cero archivos de producción tocados. Es el guardarraíl que convierte el golden-set de "regression test del input" en "contract test del extractor": detecta la clase de bug más peligrosa (extractor neutralizado) que el v1 dejaba pasar. Refuerza R1 a nivel estructural, no solo por revisión manual.

**Comando (resolución de venv — C4):**
```bash
cd "Stacky Agents/backend"
PYBIN="$(ls .venv/Scripts/python.exe 2>/dev/null || ls .venv/bin/python 2>/dev/null || command -v python)"
"$PYBIN" -m pytest tests/test_extraction_detects_pathologies.py -q
```

**Procedimiento TDD:** este test depende de que F1+F2 ya hayan cargado fixtures de ambos polos. Correrlo ANTES de F1 → rojo (corpus incompleto), lo que fuerza a que F1 incluya el caso `looks_like_epic=false`. Correrlo tras F1+F2 → verde.

**Criterio de aceptación binario:** los dos tests verdes; si se borra el último fixture de un polo, el test se vuelve rojo.

**Flag/protección:** ninguno. **Agregar a `HARNESS_TEST_FILES` (.sh y .ps1).**

**Impacto por runtime + fallback:** N/A — estático sobre el corpus, agnóstico de runtime; cubre los 3 por construcción.

**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | Un fixture sintético de M1 codifica `expect` incorrecto y "blinda" un bug, o un extractor neutralizado pasa todos los fixtures. | TDD: el `expect` se valida contra el comportamiento CORRECTO esperado (revisado a mano). **+ F7 (anti-blindaje):** meta-test estructural que exige ambos polos de discriminación, detectando extractores constantes que el fixture-por-fixture no atrapa. |
| R2 | El parseo regex de `HARNESS_TEST_FILES` (F4) se rompe si cambia el formato del `.sh`. | El regex ancla a líneas `^\s*tests/....py\s*$`; `test_ratchet_no_referencia_archivos_inexistentes` detecta desincronización. Si se reescribe el script, actualizar el regex (test fallará ruidosamente, no en silencio). |
| R3 | El centinela F5 da falsos positivos por comentarios/docstrings. | `_JUSTIFIED` con motivo `# solo en comentario`; documentado como caso borde conocido. |
| R4 | github_copilot gana runner CLI propio y nadie lo cablea a los seams. | `test_github_copilot_exception_documented` (F3) se vuelve rojo apenas se agregue a `RUNNER_SOURCES`, forzando el cableado. |
| R5 | La allowlist semilla de F4 (~69 archivos) se vuelve un basurero permanente. | El meta-test NO exige triage (fuera de DoD) pero la allowlist es visible y versionada; cada entrada lleva `# pendiente-de-triage`. El valor es el guard contra NUEVOS tests sin clasificar. |
| R6 | Importar `api.tickets` en el runner de M1 arrastra dependencias pesadas/efectos. | Verificar que el import no dispara I/O al cargar; si lo hace, el test usa `sys.path` y mockea lo mínimo. `_extract_epic_html`/`_looks_like_epic` son funciones puras sin estado de módulo. |
| R7 | Polución de suite completa enmascara verde/rojo. | Todo se corre POR ARCHIVO (memoria `stacky-backend-dev-test-env`); el ratchet ya corre uno por uno. |

---

## 6. Fuera de scope (descartado con motivo)

- **Mutation testing (mutmut/cosmic-ray):** alto costo de ejecución y de tooling, ruido en CI, beneficio marginal sobre un golden-set bien diseñado. Descartado.
- **Property-based testing general (Hypothesis):** no-determinista por diseño (shrinking, seeds), contradice el principio determinista de M1 y agrega dependencia. Descartado salvo casos puntuales futuros.
- **Pre-commit hooks:** agregarían fricción al operador y a los runtimes que no controlan el entorno local; este plan vive en tests/CI, default "se corre siempre". Descartado (viola "cero trabajo extra").
- **Captura/replay de runs completos de los 3 CLIs (cassettes):** rechazado explícitamente en §3 (paridad + no-determinismo + datos personales). M1 va sobre extractores puros.
- **AST en F5 en vez de grep:** más preciso pero más caro/complejo; el allowlist es chico (16 archivos), grep + `_JUSTIFIED` es suficiente. Reevaluable si el allowlist crece mucho.
- **Triage de los ~190 tests no clasificados (F4):** trabajo de seguimiento, NO DoD de este plan.
- **Patología "ordinal≠ADO-id" sobre el pending-task puro (C1):** NO es blindable como función pura. El `task_ado_id` es metadata de consumo que Stacky escribe DESPUÉS de crear la task en ADO (`_CONSUMED_METADATA_KEYS`, `tickets.py:62`); cuando el agente escribe el pending, el ADO-id no existe. Detectarla requiere el estado de ADO + el filesystem (lo cubre `_scan_pending_tasks_for_epic`, que NO es puro, y el desatascador). Documentado, no testeado aquí. Reevaluable como test de integración con DB de fixtures (otro plan).

---

## 7. Glosario, Orden de implementación y DoD

### Glosario
- **Golden-set / fixture congelado:** archivo JSON con un input fijo (`raw`) y su salida esperada (`expect`); se versiona y no cambia salvo decisión explícita.
- **Extractor puro:** función sin estado, sin I/O, sin reloj, sin red, que transforma un string en otro string/bool. Aquí: `_extract_epic_html`, `_looks_like_epic`, `_validate_pending_task_payload`.
- **Conformance:** suite que verifica por introspección estática que cada runtime cumple el contrato del arnés (cableado a seams + capacidades).
- **Ratchet:** lista que solo crece (`HARNESS_TEST_FILES`); garantiza que la cobertura del arnés no se encoja.
- **Centinela de no-determinismo:** meta-test estático que prohíbe fuentes de no-determinismo en módulos del núcleo.
- **Seam inyectable:** punto de inyección (parámetro `now`/`rng`) que permite controlar tiempo/azar en tests sin tocar producción.
- **Excepción documentada / degradación controlada:** cuando un runtime no soporta una capacidad, se declara explícitamente con motivo y fallback, nunca con skip mudo.

### Orden de implementación (estricto, por dependencia)
1. **F0** — andamiaje del golden-set de extracción + 1 fixture (rojo→infra).
2. **F1** — fixtures de épica/HTML (4 patologías).
3. **F2** — función pura `_validate_pending_task_payload` + fixtures pending-task.
4. **F3** — paridad de los 3 runtimes en conformance (independiente de F0-F2; puede hacerse en paralelo).
5. **F4** — meta-test de ratchet + allowlist semilla.
6. **F5** — centinela de no-determinismo.
7. **F7** — meta-test anti-blindaje (depende de F1+F2; ambos polos de fixtures presentes).
8. **F6** — registrar F0-F2/F4/F5/F7 en `HARNESS_TEST_FILES` (.sh y .ps1) y correr el ratchet completo.

### DoD global (binario)
- [ ] `python -m pytest tests/test_golden_extraction.py -q` → verde, ≥ 8 fixtures (≥ 7 `kind=epic`, ≥ 4 `kind=pending_task`, solapados o sumados a ≥ 8). **(K1)**
- [ ] `python -m pytest tests/conformance/test_runtime_conformance.py -q` → verde, con `test_runtime_declared_in_capabilities[github_copilot]` y `test_github_copilot_exception_documented` presentes. **(K2)**
- [ ] `python -m pytest tests/test_harness_ratchet_meta.py -q` → verde; un test nuevo no clasificado lo pone rojo. **(K3)**
- [ ] `python -m pytest tests/test_no_determinism_sentinel.py -q` → verde, 16 módulos vigilados. **(K4)**
- [ ] `python -m pytest tests/test_extraction_detects_pathologies.py -q` → verde, ambos polos cubiertos. **(F7 — anti-blindaje)**
- [ ] `bash scripts/run_harness_tests.sh` → `FAIL=0 MISSING=0`, exit 0; los **4** archivos nuevos en `PASS` (golden_extraction, harness_ratchet_meta, no_determinism_sentinel, extraction_detects_pathologies).
- [ ] El `.ps1` (`run_harness_tests.ps1`) lista los mismos 4 archivos con formato `"...",` (paridad de runners del ratchet).
- [ ] Todos los fixtures de M1 son sintéticos/anonimizados (sin datos personales; IDs en rango 900000+). **(G6)**
- [ ] Ningún cambio toca UI, flujos de aprobación, auth ni publica a ADO. **(G2/G3/G4)**
- [ ] Trabajo del operador en todo el plan: ninguno.
