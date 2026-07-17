# Plan 158 — Centro de Costos: fix de telemetría real en Claude Code CLI (paridad con Codex)

**Estado:** PROPUESTO v1

## 1. Título, objetivo e impacto

**Objetivo (1 párrafo):** el operador reporta "el centro de costos no está funcionando, está todo en 0".
Investigación confirmada leyendo el código (§2): el runtime `claude_code_cli` — el que usa el flujo
principal de Resolver Incidencias / desarrollo con Claude Code — nunca expone la clave canónica
`metadata["model"]` ni llama a `harness.telemetry.persist()`, a diferencia de `codex_cli` que sí lo
hace. Esto rompe el fallback de estimación de costo (`harness/pricing.estimate_cost`) del extractor
canónico `services/cost_analytics.extract_cost_row()` (Plan 142, IMPLEMENTADO, contrato NO se toca) para
cualquier ejecución `claude_code_cli` donde el CLI no reportó `total_cost_usd` explícito (plan de
suscripción, o el proceso fue matado por el stall watchdog / timeout del Plan 144 antes de emitir el
evento `result`). Este plan agrega la persistencia de telemetría real y completa (modelo + costo) al
runner de Claude Code CLI, con paridad verificada en los 3 runtimes, y decide explícitamente qué pasa
con las ejecuciones históricas ya guardadas (§2, backfill acotado y aditivo).

**KPI / impacto esperado:** el contador **"Runs sin costo"** que ya muestra `CostKpiCards.tsx:33`
(`${summary.runs_without_cost} / ${summary.runs_total}`) debe bajar para las ejecuciones nuevas de
`claude_code_cli` que sí reportan tokens de uso (aunque no reporten `total_cost_usd` explícito). Es la
señal visible para el operador de que el fix funciona — sin cambiar una sola línea de frontend.

## 2. Por qué ahora / gap que cierra (evidencia verificada archivo:línea)

### 2.1 Los DOS pipelines de costos (confirmado, no ha cambiado desde el reporte del operador)

- **Legacy** (intacto, fuera de scope — Plan 142 §6 ya decidió no tocarlo): `_execution_costs()` en
  `Stacky Agents/backend/api/metrics.py:52`, alimenta `/ticket-costs` y `/project-costs`
  (`metrics.py:78,131`). NO es lo que renderiza `CostCenterPage.tsx`.
- **Canónico** (Plan 142, IMPLEMENTADO — el que SÍ usa la UI del Centro de Costos):
  `extract_cost_row()` en `Stacky Agents/backend/services/cost_analytics.py:77-127`. Precedencia
  `harness_telemetry` (`ht`) > `claude_telemetry` legacy (`ct`) > `cost_usd` top-level
  (`cost_analytics.py:92-103`), `model` resuelto en `cost_analytics.py:86`:
  `model = md.get("model") or _ht_raw.get("model")`. Expuesto por `/metrics/cost-summary`,
  `/metrics/cost-burn`, `/metrics/cost-breakdown` (`api/metrics.py:622,655,674` según Plan 142).
  Gateado por `STACKY_COST_CENTER_ENABLED` (default `true`, `config.py:543-545` — **la flag NO es el
  problema**, ya está ON).

### 2.2 codex_cli — referencia correcta (NO tocar, es el patrón a imitar)

`Stacky Agents/backend/services/codex_cli_runner.py:808-817`:

```python
if return_code == 0:
    if _stream_telemetry_sink:
        try:
            from harness.telemetry import from_codex_event, persist as _persist_telemetry
            _t = from_codex_event(_stream_telemetry_sink)
            _persist_telemetry(execution_id, _t)
        except Exception as exc:
            log("warn", f"harness_telemetry codex: persist falló (no crítico): {exc}")
```

Codex SÍ llama `persist()`, que escribe `metadata["harness_telemetry"]`
(`Stacky Agents/backend/harness/telemetry.py:122-141`) con el fallback de estimación
(`_maybe_estimate_cost`, `telemetry.py:53-66`) ya aplicado. **codex_cli está bien. No requiere cambios.**

### 2.3 claude_code_cli — el bug real, con 3 defectos concretos verificados

Archivo: `Stacky Agents/backend/services/claude_code_cli_runner.py`.

**Defecto A — el modelo resuelto nunca llega a la clave canónica `model`.** En la construcción del
dict `metadata` (líneas 1394-1415), la línea 1400 escribe:

```python
"claude_code_model": routed_model or model_override or config.CLAUDE_CODE_CLI_MODEL or None,
```

`routed_model` se calculó en la línea 837 (`routed_model = model_override or config.CLAUDE_CODE_CLI_MODEL`)
y sigue en scope hasta el final de la función. Pero la clave se llama `claude_code_model`, NO `model`.
`cost_analytics.py:86` sólo lee `md.get("model")` (o `harness_telemetry.raw.model`) — **nunca
`claude_code_model`**. Resultado: para TODA ejecución `claude_code_cli`, `extract_cost_row()` nunca
conoce el modelo usado, así que el fallback `estimate_cost(model, tokens_in, tokens_out)`
(`harness/pricing.py:69-98`) siempre devuelve `None` (línea 79: `if not model: return None`) aunque haya
tokens disponibles.

**Defecto B — nunca se llama a `harness.telemetry.persist()`.** Grep dirigido confirmó CERO ocurrencias
de `harness_telemetry`, `from_claude_stream` o `telemetry.persist` en todo `claude_code_cli_runner.py`
(las únicas 3 coincidencias del archivo para telemetría son `_capture_result_telemetry` en las líneas
1050, 2544, y la escritura manual de `claude_telemetry` en las líneas 1452-1458). En vez de usar el
pipeline canónico, el runner escribe la clave legacy a mano:

```python
# claude_code_cli_runner.py:1450-1458
if stream_telemetry:
    session_id = stream_telemetry.get("session_id")
    if session_id:
        metadata["session_id"] = session_id
    metadata["claude_telemetry"] = {
        k: v for k, v in stream_telemetry.items() if k != "session_id"
    }
```

Esto SÍ es leído por `extract_cost_row()` como precedencia 2 (`ct.get("total_cost_usd")`,
`cost_analytics.py:98-100`) — **cuando el CLI reporta `total_cost_usd` explícito, el costo YA se ve
hoy correctamente vía esta ruta legacy**. El bug se manifiesta sólo cuando:

1. El CLI reportó `usage` (tokens) en el evento `result` pero **no** `total_cost_usd` (p. ej. cuenta de
   suscripción Claude Pro/Max en vez de facturación por token/API key) → sin `model` (Defecto A) el
   fallback de estimación nunca puede correr → `cost_kind="unknown"`, `cost_usd=None`.
2. El proceso fue matado (stall watchdog / timeout del Plan 144, `STACKY_RUNAWAY_MAX_TURNS`,
   `EXECUTION_TIMEOUT_MINUTES`) **antes** de que llegara CUALQUIER evento `result` → `stream_telemetry`
   queda `{}` (falsy) → el `if stream_telemetry:` de la línea 1452 ni siquiera entra → NO se escribe
   `claude_telemetry` en absoluto. Este caso (2) es **genuinamente irrecuperable** (no hay ningún dato
   de costo/tokens en ningún lado): se documenta como comportamiento correcto en §6, no se backfillea.

**Defecto C — `_capture_result_telemetry` (líneas 2544-2571) nunca captura `model`.** Sólo copia
`input_tokens`/`output_tokens`/`cache_read_input_tokens`/`cache_creation_input_tokens` de `usage`, y
`total_cost_usd`/`num_turns`/`is_error` del evento — nunca `model` (verificado leyendo la función
completa). Esto es irrelevante para el fix elegido (§4, F1): en vez de depender de que el stream JSON
del CLI reporte el modelo (dato no garantizado por el protocolo), el fix inyecta el modelo que **el
propio runner ya sabe que pidió** (`routed_model`, resuelto ANTES de invocar el CLI vía `--model`,
`claude_code_cli_runner.py:2059`) — más confiable que parsear el stream.

### 2.4 github_copilot — VERIFICADO, ya tiene paridad, NO requiere cambios

El operador pidió verificar explícitamente este runtime. Evidencia: el runtime `github_copilot` NO pasa
por `claude_code_cli_runner.py` ni `codex_cli_runner.py` — corre por
`Stacky Agents/backend/agent_runner.py:_run_in_background` (línea 614), que llama
`agent.run(...)` (línea 870), implementado en `Stacky Agents/backend/agents/base.py:205-247`:

```python
# agents/base.py:226-239
response = copilot_bridge.invoke(...)
metadata = dict(response.metadata or {})
```

Y `copilot_bridge.py:809-821` (función que atiende la invocación GitHub Copilot) devuelve:

```python
return BridgeResponse(
    text=text, format="markdown",
    metadata={
        "model": data.get("model") or chosen_model,   # <- YA es la clave canónica "model"
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        ...
    },
)
```

Esas claves (`model`, `tokens_in`, `tokens_out`) llegan sin transformación a
`agent_runner.py:909 md = result.metadata` → `row.metadata_dict = md` (línea 943). `extract_cost_row()`
ya lee `md.get("model")` (línea 86) y `md.get("tokens_in")`/`md.get("tokens_out")` como precedencia 3
(línea 88-89) — confirmado con el test existente `test_copilot_is_nominal_never_reported`
(`tests/test_cost_analytics_extract.py:65-86`), que verifica que un run `github_copilot` con
`model`+tokens pero sin costo reportado cae correctamente a `cost_kind="nominal"` con estimación por
pricing. **Conclusión: github_copilot ya tiene paridad real. No se toca ningún archivo de este
runtime.** (`copilot_bridge.py` nunca devuelve `cost_usd`, pero no lo necesita: es suscripción plana,
`_SUBSCRIPTION_RUNTIMES` en `cost_analytics.py:31` ya lo marca `nominal` con hint de pricing.)

### 2.5 Planes 150-157 — sin duplicación

Se escanearon los títulos de 150 (densidad adaptativa), 151 (onboarding), 152 (centro de
notificaciones), 153 (publicación ADO transaccional), 154 (arnés veraz ratchet), 156 (latido único),
157 (comparador BD). Ninguno toca telemetría de costo ni `claude_code_cli_runner.py`. Sin colisión.

## 3. Principios y guardarraíles (NO negociables)

1. **Paridad de 3 runtimes, verificada, no asumida.** codex_cli: ya correcto (§2.2), no se toca.
   claude_code_cli: el único con el bug real (§2.3), se corrige en este plan. github_copilot: ya tiene
   paridad (§2.4, verificado con evidencia), no se toca. Ningún ítem de este plan queda atado a un solo
   runtime sin fallback explícito.
2. **Cero trabajo extra para el operador.** Todo el fix es invisible/automático. Las 2 flags nuevas
   (§4, F4) son kill-switches internos, default **ON** — ninguna de las 4 excepciones duras aplica (no
   bypasea revisión humana, no es destructivo/irreversible, no depende de un prerequisito externo no
   garantizado, no reduce seguridad). "Trabajo del operador: ninguno" en cada fase salvo que se indique
   lo contrario.
3. **Human-in-the-loop innegociable.** Este plan sólo corrige telemetría de observabilidad (lo que el
   operador YA VE en el Centro de Costos); no cambia ningún flujo de aprobación, publicación ni
   ejecución autónoma.
4. **Mono-operador sin auth real.** Sin RBAC, sin multiusuario.
5. **No degradar.** El fix reusa `harness/telemetry.py` y `services/cost_analytics.py` TAL CUAL existen
   (Plan 142, contrato congelado — **cero cambios** en `extract_cost_row`, `CostRow`, `summarize`,
   `burn`, `breakdown`, ni en los endpoints `/cost-summary|cost-burn|cost-breakdown`). Sólo se corrige
   qué datos llegan a `metadata_dict` desde el runner de Claude Code CLI. Backward-compatible: la clave
   legacy `claude_code_model` NO se borra (se agrega `model` en paralelo); `claude_telemetry` legacy
   sigue escribiéndose exactamente igual que hoy.
6. **Backfill: decisión explícita (no ambigua).** Ver §4 F4-F6. Se hace un backfill ACOTADO y ADITIVO
   (copiar `claude_code_model` → `model` en filas históricas que ya tienen `claude_code_model` pero no
   `model`) porque es 100% seguro, barato e inmediatamente útil (el extractor es puro y se reevalúa en
   cada lectura — no hace falta re-derivar `harness_telemetry` histórico). NO se backfillean filas sin
   ningún dato de telemetría (proceso matado antes de `result`, §2.3 caso 2): es data irrecuperable, no
   inventada (ver §6 Fuera de scope).

## 4. Fases F0..F7

### F0 — Tests TDD (RED hoy, deben fallar) que reproducen el bug y fijan el contrato del fix

**Objetivo (1 frase):** fijar, con tests que hoy fallan por `AttributeError`/`ImportError` (la función
que testean no existe todavía), el comportamiento exacto que F1-F3 deben implementar.

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan158_claude_cli_cost_parity.py`

Contenido EXACTO (cópialo tal cual, no lo resumas ni lo cambies de forma):

```python
"""Plan 158 — Tests de paridad de telemetría de costo en claude_code_cli_runner.

F0: estos tests fallan HOY (services.claude_code_cli_runner._finalize_cost_telemetry
no existe todavía) y deben pasar después de F1+F3.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _make_fake_scope(fake_row):
    class _FakeSession:
        def get(self, model, eid):
            return fake_row

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return _FakeSession


# ---------------------------------------------------------------------------
# F1 — unidad: _finalize_cost_telemetry
# ---------------------------------------------------------------------------

def test_finalize_cost_telemetry_sets_model_key_unconditionally():
    from services import claude_code_cli_runner as r

    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    # stream_telemetry vacío (proceso matado antes de cualquier evento result) —
    # aun así "model" debe quedar seteado (Defecto A, independiente del stall).
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry={},
        routed_model="claude-sonnet-4-6",
    )
    assert metadata["model"] == "claude-sonnet-4-6"


def test_finalize_cost_telemetry_skips_persist_when_stream_empty(monkeypatch):
    from services import claude_code_cli_runner as r
    import harness.telemetry as ht_mod

    calls = []
    monkeypatch.setattr(ht_mod, "persist", lambda eid, t: calls.append((eid, t)))

    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry={},
        routed_model="claude-sonnet-4-6",
    )
    assert calls == []


def test_finalize_cost_telemetry_persists_harness_telemetry_when_stream_has_data(monkeypatch):
    from services import claude_code_cli_runner as r
    import harness.telemetry as ht_mod

    fake_row = type("R", (), {"metadata_dict": {}})()
    FakeSession = _make_fake_scope(fake_row)
    monkeypatch.setattr(ht_mod, "session_scope", lambda: FakeSession())

    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    stream_telemetry = {
        "session_id": "sess-plan158",
        "num_turns": 3,
        "is_error": False,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
        # SIN total_cost_usd — el caso que hoy rompe (Defecto A+B).
    }
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry=stream_telemetry,
        routed_model="claude-sonnet-4-6",
    )
    assert "harness_telemetry" in fake_row.metadata_dict
    ht = fake_row.metadata_dict["harness_telemetry"]
    assert ht["cost_estimated"] is True
    assert ht["total_cost_usd"] == 18.0  # 1M*3 + 1M*15 USD/Mtok (claude-sonnet-4 en harness/pricing.py)


def test_finalize_cost_telemetry_never_raises_on_persist_failure(monkeypatch):
    from services import claude_code_cli_runner as r
    import harness.telemetry as ht_mod

    def _boom(eid, t):
        raise RuntimeError("db down")

    monkeypatch.setattr(ht_mod, "persist", _boom)
    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}
    # No debe lanzar excepción (paridad con el try/except de codex_cli_runner.py:808-817).
    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata,
        stream_telemetry={"usage": {"input_tokens": 10, "output_tokens": 10}},
        routed_model="claude-sonnet-4-6",
    )
    assert metadata["model"] == "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# F1+F3 — end-to-end: metadata final (persist + merge de _mark_terminal) ->
# extract_cost_row() ya NO es "unknown".
# ---------------------------------------------------------------------------

def test_finalize_cost_telemetry_then_merge_yields_estimated_cost(monkeypatch):
    """Simula el flujo real: persist() escribe harness_telemetry en la fila
    directamente; _mark_terminal (claude_code_cli_runner.py:2894-2895) después
    hace `current_md.update(metadata)`. Replicamos ambos pasos y verificamos
    que extract_cost_row() de la unión ya no es unknown."""
    from services import claude_code_cli_runner as r
    from services.cost_analytics import extract_cost_row
    import harness.telemetry as ht_mod

    fake_row = type("R", (), {"metadata_dict": {}})()
    FakeSession = _make_fake_scope(fake_row)
    monkeypatch.setattr(ht_mod, "session_scope", lambda: FakeSession())

    stream_telemetry = {
        "session_id": "sess-plan158",
        "num_turns": 3,
        "is_error": False,
        "usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000},
    }
    metadata = {"runtime": "claude_code_cli", "claude_code_model": "claude-sonnet-4-6"}

    r._finalize_cost_telemetry(
        execution_id=1, metadata=metadata, stream_telemetry=stream_telemetry,
        routed_model="claude-sonnet-4-6",
    )

    # Simula el merge de _mark_terminal: current_md.update(metadata).
    final_md = dict(fake_row.metadata_dict)
    final_md.update(metadata)

    row = extract_cost_row(final_md)
    assert row.model == "claude-sonnet-4-6"
    assert row.cost_kind == "estimated"
    assert row.cost_usd == 18.0


def test_baseline_without_fix_is_unknown_documents_the_bug():
    """Ancla el ANTES: la metadata que produce el runner HOY (sin "model", sin
    harness_telemetry, sólo claude_telemetry con usage y sin total_cost_usd)
    es "unknown" en el extractor canónico. Este test debe seguir en verde
    ANTES y DESPUÉS del fix (documenta el bug, no lo reproduce como red)."""
    from services.cost_analytics import extract_cost_row

    md_hoy_sin_fix = {
        "runtime": "claude_code_cli",
        "claude_code_model": "claude-sonnet-4-6",  # clave vieja, extract_cost_row no la lee
        "claude_telemetry": {"usage": {"input_tokens": 1_000_000, "output_tokens": 1_000_000}},
        # sin "model", sin "harness_telemetry"
    }
    row = extract_cost_row(md_hoy_sin_fix)
    assert row.cost_kind == "unknown"
    assert row.cost_usd is None


# ---------------------------------------------------------------------------
# F4 — backfill idempotente (claude_code_model -> model en filas históricas)
# ---------------------------------------------------------------------------

def _seed_claude_exec(*, ado_id, model_key="claude_code_model", model_value="claude-sonnet-4-6",
                       has_model=False, runtime="claude_code_cli"):
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as session:
        t = Ticket(ado_id=ado_id, project="p158", stacky_project_name="p158",
                   title=f"plan158-{ado_id}", ado_state="Active")
        session.add(t)
        session.flush()

        md = {"runtime": runtime, model_key: model_value}
        if has_model:
            md["model"] = model_value
        when = datetime.utcnow()
        e = AgentExecution(
            ticket_id=t.id, agent_type="developer", status="completed",
            input_context_json="[]", started_by="test",
            started_at=when, completed_at=when + timedelta(seconds=5),
            metadata_json=json.dumps(md),
        )
        session.add(e)
        session.flush()
        return e.id


def test_backfill_claude_model_key_copies_from_claude_code_model():
    from services.cost_analytics import backfill_claude_model_key
    from db import session_scope
    from models import AgentExecution

    exec_id = _seed_claude_exec(ado_id=990101)

    result = backfill_claude_model_key()
    assert result["updated"] >= 1

    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.metadata_dict.get("model") == "claude-sonnet-4-6"


def test_backfill_claude_model_key_is_idempotent():
    from services.cost_analytics import backfill_claude_model_key
    from db import session_scope
    from models import AgentExecution

    exec_id = _seed_claude_exec(ado_id=990102, has_model=True)  # ya tiene "model"

    result = backfill_claude_model_key()
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        assert row.metadata_dict.get("model") == "claude-sonnet-4-6"

    # correrlo de nuevo no rompe nada ni duplica trabajo sobre filas ya arregladas
    result2 = backfill_claude_model_key()
    assert isinstance(result2["updated"], int)


def test_backfill_claude_model_key_ignores_other_runtimes():
    from services.cost_analytics import backfill_claude_model_key
    from db import session_scope
    from models import AgentExecution

    exec_id = _seed_claude_exec(ado_id=990103, runtime="github_copilot")

    backfill_claude_model_key()
    with session_scope() as session:
        row = session.get(AgentExecution, exec_id)
        # github_copilot no se toca (ya tiene paridad propia, §2.4)
        assert row.metadata_dict.get("model") is None
```

**Comando exacto para correr (venv real del backend, POR ARCHIVO):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan158_claude_cli_cost_parity.py" -v
```

**Criterio de aceptación F0 (binario):** el comando de arriba debe fallar HOY con `AttributeError:
module 'services.claude_code_cli_runner' has no attribute '_finalize_cost_telemetry'` (o
`ImportError` en `services.cost_analytics.backfill_claude_model_key`) en TODOS los tests salvo
`test_baseline_without_fix_is_unknown_documents_the_bug`, que debe pasar en verde ya mismo (documenta
el bug tal cual existe hoy). **Trabajo del operador: ninguno** (sólo ejecutar el comando).

---

### F1 — Implementar `_finalize_cost_telemetry()` en `claude_code_cli_runner.py`

**Objetivo (1 frase) y valor:** una función pura y aislada que expone la clave canónica `model` y
persiste `harness_telemetry` para claude_code_cli, con paridad exacta con el patrón de
`codex_cli_runner.py:808-817` — hace pasar los tests unitarios de F0.

**Archivo a editar:** `Stacky Agents/backend/services/claude_code_cli_runner.py`

**Dónde insertar:** inmediatamente después de la función `_capture_result_telemetry` (termina en la
línea 2571, justo antes de `def _parse_claude_code_line(` en la línea 2574). Insertar la función nueva
ANTES de `_parse_claude_code_line`.

**Código EXACTO a agregar:**

```python
def _finalize_cost_telemetry(
    execution_id: int,
    metadata: dict,
    stream_telemetry: dict,
    routed_model: str | None,
) -> None:
    """Plan 158 F1 — expone metadata["model"] (clave canónica que lee
    cost_analytics.extract_cost_row) y persiste harness_telemetry canónico,
    con paridad exacta con codex_cli_runner.py:808-817.

    Defecto A (plan 158 §2.3): el modelo resuelto sólo vivía en
    metadata["claude_code_model"], nunca en metadata["model"]. Este método
    setea AMBAS claves — "claude_code_model" no se borra (retro-compat).

    Defecto B (plan 158 §2.3): claude_code_cli_runner nunca llamaba
    harness.telemetry.persist(), a diferencia de codex_cli_runner. Sin esa
    llamada, metadata["harness_telemetry"] nunca existe para este runtime y
    el fallback de estimación de costo (_maybe_estimate_cost) nunca corre.

    Nunca lanza: cualquier fallo de persist() se loguea como warning (no
    crítico), igual que el try/except de codex_cli_runner.py:816-817.
    """
    resolved_model = routed_model or metadata.get("claude_code_model")
    metadata["model"] = resolved_model
    if not stream_telemetry:
        return
    try:
        from harness.telemetry import from_claude_stream, persist as _persist_telemetry

        _stream_for_telemetry = dict(stream_telemetry)
        _stream_for_telemetry.setdefault("model", resolved_model)
        _t = from_claude_stream(_stream_for_telemetry)
        _persist_telemetry(execution_id, _t)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[exec={execution_id}] harness_telemetry claude: persist falló (no crítico): {exc}"
        )
```

**Tests que este paso hace pasar (de F0):**
`test_finalize_cost_telemetry_sets_model_key_unconditionally`,
`test_finalize_cost_telemetry_skips_persist_when_stream_empty`,
`test_finalize_cost_telemetry_persists_harness_telemetry_when_stream_has_data`,
`test_finalize_cost_telemetry_never_raises_on_persist_failure`.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan158_claude_cli_cost_parity.py" -v -k "finalize_cost_telemetry"
```

**Criterio de aceptación (binario):** los 4 tests de arriba en verde; el resto de F0 sigue rojo (todavía
no está wireado ni existe el backfill — eso es F3/F4).

**Impacto por runtime:** sólo `claude_code_cli` (función nueva, no invocada aún desde el flujo
principal — eso es F3). `codex_cli` y `github_copilot`: cero impacto, cero líneas tocadas.
**Trabajo del operador: ninguno.**

---

### F2 — Flags: atributos en `config.py` (necesario antes de F3)

**Objetivo (1 frase) y valor:** declarar los 2 kill-switches que protegen F3 y F6, para que
`config.STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED` y
`config.STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED` sean legibles en runtime ANTES de que F3 los use.

**Archivo a editar:** `Stacky Agents/backend/config.py`

**Dónde insertar:** inmediatamente después del bloque `# ── Plan 142 — Centro de Costos + Codeburn`
(después de la línea 549, donde termina `STACKY_COST_CODEBURN_IMPORT_ENABLED`). Buscar con grep el
texto `STACKY_COST_CODEBURN_IMPORT_ENABLED` en `config.py` para ubicar el punto exacto.

**Código EXACTO a agregar:**

```python
    # ── Plan 158 — Fix telemetría de costo claude_code_cli (paridad con codex) ──
    # Kill-switch: default ON (bug fix de observabilidad, ninguna de las 4
    # excepciones duras aplica). OFF revierte al comportamiento previo exacto.
    STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED: bool = os.getenv(
        "STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED", "true"
    ).strip().lower() == "true"
    # Backfill idempotente y aditivo de metadata["model"] en filas históricas
    # de claude_code_cli (copia desde claude_code_model). Default ON: sólo
    # copia una clave ya presente, nunca inventa datos (§6 fuera de scope).
    STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED: bool = os.getenv(
        "STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED", "true"
    ).strip().lower() == "true"
```

**Test:** no hay test dedicado a config.py en este proyecto (los flags se validan en
`test_harness_flags.py`, ver F5). **Criterio de aceptación (binario):** `python -c "from config import
config; print(config.STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED,
config.STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED)"` corrido desde
`Stacky Agents/backend/.venv/Scripts/python.exe` imprime `True True` sin excepción.

**Trabajo del operador: ninguno** (default ON; desactivable desde el panel de flags una vez completado F5).

---

### F3 — Wirear `_finalize_cost_telemetry()` en el flujo principal del runner

**Objetivo (1 frase) y valor:** conectar la función de F1 al flujo real de ejecución, detrás del
kill-switch de F2 — hace pasar el test end-to-end de F0 y resuelve el bug para ejecuciones NUEVAS.

**Archivo a editar:** `Stacky Agents/backend/services/claude_code_cli_runner.py`

**Ubicación exacta:** dentro del bloque `if stream_telemetry:` de las líneas 1452-1458 (el que hoy
construye `metadata["claude_telemetry"]`). Reemplazar:

```python
        # F1.2 — telemetría nativa persistida en metadata. session_id va
        # top-level: habilita F2.3 (--resume) sin re-parsear nada.
        if stream_telemetry:
            session_id = stream_telemetry.get("session_id")
            if session_id:
                metadata["session_id"] = session_id
            metadata["claude_telemetry"] = {
                k: v for k, v in stream_telemetry.items() if k != "session_id"
            }
```

por:

```python
        # F1.2 — telemetría nativa persistida en metadata. session_id va
        # top-level: habilita F2.3 (--resume) sin re-parsear nada.
        if stream_telemetry:
            session_id = stream_telemetry.get("session_id")
            if session_id:
                metadata["session_id"] = session_id
            metadata["claude_telemetry"] = {
                k: v for k, v in stream_telemetry.items() if k != "session_id"
            }
        # Plan 158 — paridad de telemetría de costo con codex_cli (kill-switch).
        # Se llama SIEMPRE (incluso con stream_telemetry vacío) para que
        # metadata["model"] quede seteado aunque el proceso haya sido matado
        # antes de un evento result (Defecto A es independiente del stall).
        if config.STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED:
            _finalize_cost_telemetry(
                execution_id=execution_id,
                metadata=metadata,
                stream_telemetry=stream_telemetry,
                routed_model=routed_model,
            )
```

**Nota de diseño explícita (no ambigua):** a diferencia de codex (`if return_code == 0:`, sólo persiste
en éxito), este wiring NO condiciona a `return_code == 0` — replica el comportamiento YA EXISTENTE de
`metadata["claude_telemetry"]` (líneas 1452-1458), que se escribe sin importar el código de salida
mientras haya habido un evento `result`. Esto es intencional y MEJOR que codex: captura telemetría
parcial también en runs que terminan en error/needs_review, siempre que el CLI haya alcanzado a
reportar un `result`. No es una regresión: es paridad con el comportamiento legacy ya probado.

**Test que este paso hace pasar (de F0):** `test_finalize_cost_telemetry_then_merge_yields_estimated_cost`
— técnicamente ese test llama a `_finalize_cost_telemetry` directamente (unitario), así que YA pasaba
desde F1. Este paso F3 es el que hace que el comportamiento real del proceso `claude` (subprocess real)
también lo tenga. Verificación de wiring (no hay test de integración de subprocess real en este repo
para este runner — mismo patrón que el resto de `test_claude_code_cli_phase1.py`): confirmar con grep
que la llamada quedó insertada.

**Comando exacto (regresión sobre el archivo completo del runner, no sólo el nuevo):**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_claude_code_cli_phase1.py" "Stacky Agents/backend/tests/test_plan158_claude_cli_cost_parity.py" -v
```

**Criterio de aceptación (binario):** ambos archivos en verde completo; ningún test preexistente de
`test_claude_code_cli_phase1.py` se rompe (paridad de calidad F1.1/F1.2/F1.4/§5.3 intactas).

**Flag que protege este cambio:** `STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED`, default **ON**
(§3.2 — ninguna de las 4 excepciones duras aplica; es un kill-switch de rollback instantáneo, no una
feature opt-in). Con OFF, el runner se comporta EXACTAMENTE como hoy (bit a bit): no llama
`_finalize_cost_telemetry`, `metadata["model"]` nunca se setea, `harness_telemetry` nunca se persiste.

**Impacto por runtime:** `claude_code_cli` (único archivo tocado). `codex_cli`/`github_copilot`: cero
impacto — ninguno de esos runners importa ni depende de `claude_code_cli_runner.py`.
**Trabajo del operador: ninguno** (default ON).

---

### F4 — Backfill idempotente y aditivo (`services/cost_analytics.py`)

**Objetivo (1 frase) y valor:** para ejecuciones YA GUARDADAS de `claude_code_cli` que tienen
`claude_code_model` (siempre presente, es la clave vieja no removida) pero no `model`, copiar el valor
una sola vez — hace que el Centro de Costos muestre correctamente el histórico sin re-ejecutar nada.
**Decisión explícita de scope (§3.6, §6):** SÓLO copia una clave que ya existe (100% seguro, sin
inventar costo). NO intenta reconstruir `harness_telemetry` histórico ni estimar costo para filas sin
ningún dato de tokens (Defecto B caso 2, proceso matado antes de `result`): esas filas siguen
`cost_kind="unknown"` legítimamente, documentado en §6.

**Archivo a editar:** `Stacky Agents/backend/services/cost_analytics.py`

**Dónde insertar:** al final del archivo, después de `load_external_codeburn` (después de la línea
537, que es la última línea del archivo hoy).

**Código EXACTO a agregar:**

```python
# ─────────────────────────────────────────────────────────────────────────────
# Plan 158 F4 — backfill idempotente y aditivo: copia metadata["claude_code_model"]
# -> metadata["model"] en filas históricas de claude_code_cli que no tienen
# "model". NUNCA inventa datos: si claude_code_model tampoco existe, no hace
# nada con esa fila (queda "unknown" legítimamente, ver plan158 §6).
# ─────────────────────────────────────────────────────────────────────────────

_BACKFILL_MAX_ROWS = 20000  # mismo cap duro de seguridad que _MAX_ROWS (mono-operador)


def backfill_claude_model_key() -> dict:
    """Copia claude_code_model -> model en filas claude_code_cli sin "model".

    PURO en su lógica de decisión (sólo copia una clave existente), pero SÍ
    toca DB (lectura + escritura acotada por _BACKFILL_MAX_ROWS). Idempotente:
    correrlo N veces produce el mismo resultado final; en la segunda corrida
    "updated" es 0 para las filas ya arregladas.

    Devuelve {"scanned": N, "updated": M}.
    """
    from db import session_scope
    from models import AgentExecution

    scanned = 0
    updated = 0
    with session_scope() as session:
        rows = (
            session.query(AgentExecution)
            .order_by(AgentExecution.id.desc())
            .limit(_BACKFILL_MAX_ROWS)
            .all()
        )
        for row in rows:
            scanned += 1
            md = row.metadata_dict
            if md.get("runtime") != "claude_code_cli":
                continue
            if md.get("model") is not None:
                continue
            claude_model = md.get("claude_code_model")
            if not claude_model:
                continue
            md["model"] = claude_model
            row.metadata_dict = md
            updated += 1
    return {"scanned": scanned, "updated": updated}
```

**Tests (ya escritos en F0, ahora deben pasar):**
`test_backfill_claude_model_key_copies_from_claude_code_model`,
`test_backfill_claude_model_key_is_idempotent`,
`test_backfill_claude_model_key_ignores_other_runtimes`.

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan158_claude_cli_cost_parity.py" -v -k "backfill"
```

**Criterio de aceptación (binario):** los 3 tests de backfill en verde; el resto de F0 (finalize_cost_telemetry
+ end-to-end) también en verde a esta altura (F1+F3 ya aplicados). Con esto, **`test_plan158_claude_cli_cost_parity.py`
completo debe estar en verde**, salvo el test ancla `test_baseline_without_fix_is_unknown_documents_the_bug`
que sigue en verde (documenta el "antes", no cambia).

**Flag que protege este cambio:** `STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED` (F2), default **ON**
— gatea el DISPARO automático en F6, no la función en sí (la función siempre existe y es segura de
llamar manualmente; el flag sólo controla si corre sola al arrancar).

**Impacto por runtime:** sólo filas con `runtime == "claude_code_cli"` en `metadata_dict`; cualquier
otra fila (`codex_cli`, `github_copilot`, `mock`, vacías) se ignora explícitamente (test
`test_backfill_claude_model_key_ignores_other_runtimes`). **Trabajo del operador: ninguno.**

---

### F5 — Registrar las 2 flags en el panel del arnés (`harness_flags.py`)

**Objetivo (1 frase) y valor:** que el operador pueda ver y, si quiere, apagar los kill-switches de F3/F6
desde la UI del panel de flags (sub-tab Arnés), sin tocar código ni `.env`. Patrón canónico triple
default ON, idéntico al usado por `STACKY_COST_CENTER_ENABLED` en Plan 142
(`docs/142_PLAN_CENTRO_DE_COSTOS_CODEBURN_KPIS_TOKENS_MULTIDIMENSIONAL.md` §F3).

**Archivos a editar (2):**

**1. `Stacky Agents/backend/services/harness_flags.py`**

a) Agregar al `FLAG_REGISTRY`, inmediatamente después del bloque `# ── Plan 142 — Centro de Costos +
Codeburn` (después del `FlagSpec` de `STACKY_COST_CODEBURN_IMPORT_PATH`, alrededor de la línea 1639).
Buscar con grep el texto `STACKY_COST_CODEBURN_IMPORT_PATH` dentro de `FLAG_REGISTRY` para ubicar el
punto exacto:

```python
    # ── Plan 158 — Fix telemetría de costo claude_code_cli ─────────────────────
    FlagSpec(
        key="STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED",
        type="bool",
        default=True,
        label="Centro de Costos: telemetría real claude_code_cli",
        description=(
            "Plan 158 — Persiste harness_telemetry + metadata['model'] canónico "
            "en ejecuciones claude_code_cli (paridad con codex_cli). Kill-switch: "
            "OFF revierte al comportamiento previo exacto (sin cambios de datos)."
        ),
        group="observabilidad",
    ),
    FlagSpec(
        key="STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED",
        type="bool",
        default=True,
        label="Centro de Costos: backfill de modelo histórico (claude_code_cli)",
        description=(
            "Plan 158 — Al arrancar, copia una sola vez metadata['claude_code_model'] "
            "-> metadata['model'] en ejecuciones históricas de claude_code_cli que ya "
            "tienen la clave vieja pero no la canónica. Idempotente, aditivo, nunca "
            "inventa costo."
        ),
        group="observabilidad",
    ),
```

b) Agregar ambas keys a `_CATEGORY_KEYS["observabilidad_notif"]` (la tupla que ya contiene
`"STACKY_COST_CENTER_ENABLED", "STACKY_COST_CODEBURN_IMPORT_ENABLED"`, línea 262):

```python
        "STACKY_COST_CENTER_ENABLED", "STACKY_COST_CODEBURN_IMPORT_ENABLED",
        "STACKY_COST_CODEBURN_IMPORT_PATH",  # Plan 142
        "STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED",  # Plan 158
        "STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED",  # Plan 158
```

**2. `Stacky Agents/backend/tests/test_harness_flags.py`**

Agregar ambas keys al set `_CURATED_DEFAULTS_ON` (línea 467, mismo bloque donde ya está
`"STACKY_COST_CENTER_ENABLED"`):

```python
    "STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED",  # Plan 158
    "STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED",  # Plan 158
```

Y agregar un test nuevo (mismo patrón que `test_cost_center_flag_registered_default_on`,
línea 933-948):

```python
def test_plan158_claude_cli_telemetry_flags_registered_default_on():
    """Plan 158 — las 2 flags de telemetría claude_code_cli: registradas, categorizadas, default ON."""
    from services.harness_flags import FLAG_REGISTRY, categorize

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in (
        "STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED",
        "STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED",
    ):
        assert key in by_key
        assert by_key[key].default is True
        assert categorize(key) == "observabilidad_notif"
        assert key in _CURATED_DEFAULTS_ON
```

**NO regenerar `harness_defaults.env`** (misma guía permanente que Plan 142 F3: el generador hornea del
`.env` del deploy vivo; la flag es legible por `config.py` sin tocar ese archivo).

**Comando exacto:**

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -v
```

**Criterio de aceptación (binario):** `test_harness_flags.py` verde completo, incluyendo
`test_every_registry_flag_is_categorized`, `test_default_known_only_for_curated`, y el nuevo
`test_plan158_claude_cli_telemetry_flags_registered_default_on`.

**Activable/desactivable desde UI:** al estar en `FLAG_REGISTRY` + `_CATEGORY_KEYS`, el
`HarnessFlagsPanel` genérico las renderiza y togglea sin código de frontend adicional (mismo mecanismo
que toda otra flag del arnés). **Trabajo del operador: ninguno** (default ON; puede desactivarlas con
un click si quiere).

---

### F6 — Disparar el backfill una vez al arrancar el backend

**Objetivo (1 frase) y valor:** que el backfill de F4 corra automáticamente (sin acción del operador),
una sola vez, la primera vez que el backend arranca con este plan implementado.

**Archivo a editar:** `Stacky Agents/backend/app.py`

**Dónde insertar:** inmediatamente después de la línea `_startup_sync(logger)` (línea 404 — el punto
donde `create_app()` ya dispara la sincronización de tickets al arrancar). Agregar una función nueva
`_plan158_maybe_backfill_claude_model(logger)` definida cerca de `_startup_sync` (mismo archivo,
después de su definición, antes de la línea 404 donde se invoca), y llamarla justo después de
`_startup_sync(logger)`:

```python
def _plan158_maybe_backfill_claude_model(logger) -> None:
    """Plan 158 F6 — corre backfill_claude_model_key() una sola vez (marker file).

    Nunca bloquea ni rompe el arranque: cualquier excepción se loguea y se
    sigue. Con la flag OFF, no hace nada (ni siquiera chequea el marker).
    """
    if not getattr(config, "STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED", True):
        return
    try:
        from runtime_paths import data_dir
        marker = data_dir() / "plan158_claude_model_backfill.done"
        if marker.exists():
            return
        from services.cost_analytics import backfill_claude_model_key
        result = backfill_claude_model_key()
        logger.info(
            "plan158 backfill claude_code_model->model: scanned=%d updated=%d",
            result["scanned"], result["updated"],
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(datetime.utcnow().isoformat(), encoding="utf-8")
    except Exception:
        logger.exception("plan158 backfill falló (no crítico, se reintenta en el próximo arranque)")
```

Y en el punto de la línea 404:

```python
    _startup_sync(logger)
    _plan158_maybe_backfill_claude_model(logger)
```

**Nota:** si `datetime` no está importado a nivel de módulo en `app.py`, usar el import ya existente
(verificar con grep `from datetime import` al inicio del archivo antes de agregar uno duplicado — si ya
existe `datetime.utcnow` en uso en otras partes de `app.py`, reusar ese import).

**Test:** no hay test de arranque completo de `create_app()` con backfill en este plan (sería un test
de integración pesado, fuera de proporción para un marker file). Verificación manual (F7).

**Criterio de aceptación (binario):** arrancar el backend una vez
(`"Stacky Agents/backend/.venv/Scripts/python.exe" app.py` o el comando de arranque habitual del
deploy) y confirmar en el log la línea `plan158 backfill claude_code_model->model: scanned=... updated=...`;
confirmar que el archivo `data_dir()/plan158_claude_model_backfill.done` existe después; arrancar una
segunda vez y confirmar que la línea de log NO vuelve a aparecer (el marker ya existe).

**Flag que protege este cambio:** `STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED` (F2), default **ON**.

**Impacto por runtime:** el backfill sólo toca filas `claude_code_cli` (F4 ya filtra por runtime); cero
impacto en `codex_cli`/`github_copilot`. **Trabajo del operador: ninguno** — corre solo, una vez, en
background del arranque normal (no bloquea el health check ni retrasa el primer request; el query está
acotado a `_BACKFILL_MAX_ROWS=20000` filas).

---

### F7 — Verificación final y señal operador-visible (sin código nuevo)

**Objetivo (1 frase) y valor:** confirmar que el fix es real desde la perspectiva del operador, no sólo
desde tests unitarios — cerrar el ciclo con la señal que el operador ya puede ver hoy en la UI.

**Pasos (todos de verificación, ningún archivo nuevo):**

1. Correr la suite completa nueva/tocada por archivo (patrón obligatorio del repo — nunca la suite
   completa junta, por contaminación cross-test conocida):

   ```
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan158_claude_cli_cost_parity.py" -v
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_claude_code_cli_phase1.py" -v
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_telemetry.py" -v
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_cost_analytics_extract.py" -v
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_cost_analytics_aggregate.py" -v
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_cost_center_api.py" -v
   "Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -v
   ```

   Todos deben quedar en verde completo (ninguno se toca en su contrato, sólo se agrega código nuevo
   aditivo — no debe romperse ninguno de estos 6 archivos preexistentes).

2. **Registrar los 7 archivos de test tocados/creados en `HARNESS_TEST_FILES`** (patrón obligatorio del
   repo — un `test_*.py` nuevo que no se registra rompe el meta-test del ratchet). Archivo:
   `Stacky Agents/backend/run_harness_tests.sh` (o el archivo equivalente que enumera
   `HARNESS_TEST_FILES` — confirmar el nombre exacto del archivo con
   `grep -rn "HARNESS_TEST_FILES" "Stacky Agents/backend"` antes de editar). Agregar la línea del
   archivo nuevo: `test_plan158_claude_cli_cost_parity.py`.

3. **Señal operador-visible (manual, opcional, no bloqueante):** con el backend corriendo y al menos
   una ejecución NUEVA de `claude_code_cli` completada después de este fix, abrir el Centro de Costos
   en la UI y confirmar que el contador **"Runs sin costo"** (`CostKpiCards.tsx:33`) para esa ejecución
   NO la cuenta como sin costo (baja el numerador respecto de antes del fix), o que aparece con
   `cost_kind="estimated"` en la tabla de runs. Este paso es la confirmación end-to-end real, pero NO es
   parte del criterio binario de aceptación del plan (requiere una ejecución real del CLI, fuera del
   control determinista de un test).

**Criterio de aceptación (binario) de F7:** los 7 comandos pytest del paso 1 en verde; el archivo de
test nuevo aparece en `HARNESS_TEST_FILES`. **Trabajo del operador: ninguno** para los pasos 1-2 (los
corre quien implementa); el paso 3 es opcional y sólo para confirmación visual del propio operador si
lo desea.

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | `_finalize_cost_telemetry` lanza una excepción no controlada y rompe el runner en medio de un run real. | Todo el cuerpo que puede fallar (import + `from_claude_stream` + `persist`) está en `try/except Exception` con log `warning`, idéntico al patrón ya probado en producción de `codex_cli_runner.py:808-817`. La asignación `metadata["model"] = resolved_model` es una simple asignación de dict, no puede lanzar. |
| R2 | `persist()` abre su propio `session_scope()` separado del que usa `_mark_terminal()` más adelante — posible condición de carrera o doble escritura. | Es EXACTAMENTE el mismo patrón que ya usa `codex_cli_runner.py` en producción hoy (mismo `persist()`, mismo `_mark_terminal` merge downstream vía `current_md.update(metadata)` en la línea 2895). Cero riesgo nuevo: se extiende un patrón ya probado, no se inventa uno. |
| R3 | El backfill (F4/F6) escanea hasta 20000 filas al arrancar y retrasa el boot. | Cap duro `_BACKFILL_MAX_ROWS=20000` (mismo orden de magnitud que `_MAX_ROWS` de `cost_analytics.load_records`, ya proporcionado para mono-operador). Marker file evita repetir el escaneo en arranques subsiguientes — corre UNA sola vez en la vida del deploy. Si el operador quiere reforzarlo, puede desactivar la flag F2. |
| R4 | El backfill corrompe o pisa datos existentes de ejecuciones históricas. | La función SOLO escribe si `md.get("model") is None` (nunca pisa un valor ya presente) y SOLO copia un valor que ya existe en la misma fila (`claude_code_model`) — no inventa, no borra ninguna clave. Cubierto por `test_backfill_claude_model_key_is_idempotent`. |
| R5 | Romper el contrato congelado de `extract_cost_row`/`cost_analytics.py` del Plan 142. | Cero líneas de `extract_cost_row`, `CostRow`, `summarize`, `burn`, `breakdown` se tocan — se agrega SOLO una función nueva al final del archivo (`backfill_claude_model_key`), verificado en F4. `test_cost_analytics_extract.py`/`test_cost_analytics_aggregate.py` deben seguir verdes sin modificación (F7 paso 1). |
| R6 | Romper `test_harness_flags.py` al agregar 2 flags nuevas. | Patrón canónico triple coherente en los 3 puntos (F2 `config.py` + F5 `FlagSpec.default=True` + F5 `_CURATED_DEFAULTS_ON`), idéntico byte a byte al usado por Plan 142 para `STACKY_COST_CENTER_ENABLED` — ya verificado que ese patrón no rompe el ratchet `test_default_known_only_for_curated`. |
| R7 | El operador corre `claude_code_cli` bajo un plan de suscripción (OAuth) donde el CLI directamente nunca reporta `total_cost_usd` ni siquiera parcialmente. | Cubierto: el fallback de estimación (`_maybe_estimate_cost` en `harness/telemetry.py:53-66`, ya existente, no se toca) calcula el costo desde tokens + modelo — que es exactamente lo que este plan garantiza que esté disponible (Defecto A). El resultado se clasifica `cost_kind="estimated"`, visible como tal en la UI (no se disfraza de "reportado"). |

## 6. Fuera de scope (explícito)

- **Backfill de `harness_telemetry` histórico completo.** No se reconstruye `harness_telemetry` para
  filas viejas — no hace falta: `extract_cost_row()` es puro y se reevalúa en cada lectura, y ya lee
  `claude_telemetry.total_cost_usd` (precedencia 2) directamente de metadata histórico cuando existe.
  Sólo se backfillea la clave `model` (F4), que es lo mínimo necesario para desbloquear el fallback de
  estimación en filas donde `claude_telemetry` tiene `usage` pero no `total_cost_usd`.
- **Filas sin ningún dato de telemetría** (proceso `claude_code_cli` matado por el stall
  watchdog/timeout ANTES de cualquier evento `result`, §2.3 Defecto B caso 2). Es data genuinamente
  irrecuperable: no hay tokens, no hay modelo confirmado usado en esa ejecución específica, no hay nada
  que copiar ni estimar. Quedan `cost_kind="unknown"` legítimamente — el contador "Runs sin costo" de
  la UI (`CostKpiCards.tsx:33`) ya comunica esto honestamente al operador, sin necesidad de cambios de
  UI.
- **Modificar `_execution_costs()`/`/ticket-costs`/`/project-costs` legacy** (`api/metrics.py:52-149`).
  Plan 142 §6 ya decidió no tocarlos para no regresionar; este plan no reabre esa decisión.
- **Cambios en `copilot_bridge.py`, `agent_runner.py`, `agents/base.py`.** Verificado con evidencia
  (§2.4) que `github_copilot` ya tiene paridad real — cero cambios en esos archivos.
- **Cambios de frontend.** El contador `runs_without_cost` y la clasificación `cost_kind` ya se
  renderizan (`CostKpiCards.tsx:33`, Plan 142 F6 IMPLEMENTADO); este plan sólo corrige qué datos llegan
  al backend. Ningún archivo `.tsx`/`.ts` se toca.
- **Agregar `--model` al capture del stream JSON (`_capture_result_telemetry`).** Descartado en favor
  de inyectar el modelo que el runner YA conoce (`routed_model`, resuelto antes de invocar el CLI) — más
  simple, más confiable, no depende del schema del stream de un binario externo.

## 7. Glosario, Orden de implementación y DoD

### Glosario

- **`AgentExecution.metadata_dict`** (`models.py:259-264`): propiedad que serializa/deserializa
  `metadata_json` (columna `Text`) a un `dict` Python. NO es una columna indexada — cualquier filtro
  por su contenido (p. ej. `runtime`) se hace en Python después de leer filas, no en SQL.
- **`RunTelemetry`** (`harness/telemetry.py:28-50`): dataclass con los campos comunes de telemetría
  (`runtime`, `session_id`, `total_cost_usd`, `input_tokens`, `output_tokens`, `cache_read_tokens`,
  `cost_estimated`). `persist()` la escribe en `metadata["harness_telemetry"]`.
- **`extract_cost_row()`** (`services/cost_analytics.py:77-127`): función PURA (sin DB) que reconcilia
  `harness_telemetry`/`claude_telemetry`/top-level en un único `CostRow` con `cost_kind` clasificado
  (`reported`/`estimated`/`nominal`/`unknown`). Contrato congelado del Plan 142 — este plan NO lo toca.
- **`cost_kind`**: clasificación de la confiabilidad del costo. `reported` = el proveedor lo informó
  explícito. `estimated` = calculado desde tokens vía `harness/pricing.estimate_cost`. `nominal` =
  runtime de suscripción plana (sólo `github_copilot` hoy), nunca facturable. `unknown` = no hay ningún
  dato (nunca se inventa `0.0`).
- **`routed_model`**: variable local de `claude_code_cli_runner.py` (línea 837) con el modelo
  efectivamente resuelto para invocar el CLI (`model_override` explícito, o `config.CLAUDE_CODE_CLI_MODEL`
  por default), pasado al subproceso vía `--model` (línea 2059).
- **Runner**: el módulo (`claude_code_cli_runner.py` / `codex_cli_runner.py`) que orquesta el
  subproceso del CLI correspondiente, parsea su stream JSON, y persiste el resultado en
  `AgentExecution`.
- **Backfill**: migración de datos idempotente y aditiva sobre filas ya existentes en la base — en este
  plan, copiar una clave ya presente (`claude_code_model` → `model`), nunca inventar datos nuevos.

### Orden de implementación (numerado, por dependencia)

1. **F0** — tests TDD (rojo por diseño, salvo el test ancla). Ningún archivo de producción tocado
   todavía.
2. **F1** — `_finalize_cost_telemetry()` en `claude_code_cli_runner.py` (función nueva, no wireada
   aún). Hace pasar los 4 tests unitarios de F0.
3. **F2** — 2 flags en `config.py` (prerequisito de F3/F6).
4. **F3** — wiring de `_finalize_cost_telemetry()` en el flujo principal, detrás de la flag de F2.
5. **F4** — `backfill_claude_model_key()` en `cost_analytics.py`. Hace pasar los 3 tests de backfill de
   F0.
6. **F5** — registro de las 2 flags en `harness_flags.py` + `_CURATED_DEFAULTS_ON` (panel UI).
7. **F6** — disparo automático del backfill al arrancar (`app.py`), detrás de la flag de F2/F5.
8. **F7** — verificación final: 7 archivos de test en verde, registro en `HARNESS_TEST_FILES`, señal
   operador-visible opcional.

### Definición de Hecho (DoD) global

- [ ] F0: `test_plan158_claude_cli_cost_parity.py` existe y falla HOY (antes de F1) salvo el test ancla.
- [ ] F1: 4 tests unitarios de `_finalize_cost_telemetry` en verde.
- [ ] F2: `config.STACKY_COST_CLAUDE_CLI_TELEMETRY_PARITY_ENABLED` y
      `config.STACKY_COST_CLAUDE_MODEL_BACKFILL_ENABLED` legibles, ambos `True` por default.
- [ ] F3: `test_plan158_claude_cli_cost_parity.py::test_finalize_cost_telemetry_then_merge_yields_estimated_cost`
      en verde; `test_claude_code_cli_phase1.py` sigue 100% verde (sin regresión).
- [ ] F4: 3 tests de backfill en verde; `cost_analytics.py` no modifica ninguna función preexistente,
      sólo agrega `backfill_claude_model_key` al final.
- [ ] F5: `test_harness_flags.py` verde completo, incluyendo el test nuevo de las 2 flags de Plan 158.
- [ ] F6: log de arranque confirma el backfill corriendo una vez; marker file presente; segundo
      arranque no repite el backfill.
- [ ] F7: los 7 archivos de test listados corren en verde POR ARCHIVO (nunca la suite completa junta);
      `test_plan158_claude_cli_cost_parity.py` registrado en `HARNESS_TEST_FILES`.
- [ ] Guardarraíles: cero cambios en `extract_cost_row`/`CostRow`/endpoints `/cost-summary|burn|breakdown`
      (Plan 142 intacto); cero cambios en `copilot_bridge.py`/`agent_runner.py`/`agents/base.py`
      (github_copilot ya tenía paridad, verificado §2.4); cero cambios de frontend; ambas flags nuevas
      default **ON** — "Trabajo del operador: NINGUNO".
