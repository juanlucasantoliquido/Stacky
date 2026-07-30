"""
test_plan274_consolidation.py — Plan 274 F7.

Que el presupuesto de 6 minutos sirva, que el timeout por caso salga de datos y
no de un numero magico, y que quede ESCRITO que falta exactamente para paralelizar.

EL GATE DE F7.1 ES AST, NO `grep -c`. `_check_deadline` es un closure ANIDADO en
`_run_pipeline_stages` (`:1324` / `:1406`): llamarlo desde otra funcion es
NameError en runtime y `compileall` da VERDE. Peor: con el gate del v2
(`grep -c "_check_deadline(" >= 9`) METER EL BUG SUBIA EL PUNTAJE. Un gate que
premia el defecto no es un gate.

F7.2 TIENE DOS MITADES Y LAS DOS SON OBLIGATORIAS. `record_run` tenia 0 callers
de produccion, asi que `_load(playbook_id)` devolvia {}, `p95_duration_ms` era 0
y `recommend_timeout_ms` salia por `if p95 <= 0: return default_ms` en el 100 %
de las corridas, PARA SIEMPRE. Conectar solo el lector deja la feature inerte con
los tests en verde: es el patron "runner sin loop por caso" del plan 262.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[2]
PIPELINE = TOOL_ROOT / "qa_uat_pipeline.py"
RUNNER = TOOL_ROOT / "uat_test_runner.py"

PLAYBOOK_ID = "uat_runner_all_specs"

# Claves fuera del scope de _check_deadline: usarlas es NameError garantizado.
CLAVES_PROHIBIDAS = ("dossier", "epic_rollup", "evidence", "functional_verdict",
                     "intent_parser", "publisher", "synthetic_ticket_builder")


def _llamadas_check_deadline() -> tuple[set[int], set[int]]:
    """(todas, en_scope) — implementa el comando C-8 con `ast`."""
    tree = ast.parse(PIPELINE.read_text(encoding="utf-8"))
    host = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_run_pipeline_stages")
    def _calls(root):
        return {n.lineno for n in ast.walk(root)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_check_deadline"}
    return _calls(tree), _calls(host)


def test_deadline_en_ocho_etapas():
    """8 llamadas + 1 definicion = 9 lineas.

    Se cuentan LLAMADAS con `\\b` y excluyendo la linea del `def`, porque
    `_check_deadline(` como subcadena tambien matchea dentro de la definicion.
    """
    todas, _ = _llamadas_check_deadline()
    assert len(todas) == 8, (
        f"KPI-5: hay {len(todas)} llamadas a _check_deadline (lineas "
        f"{sorted(todas)}); el plan pide 8 (2 previas + 6 nuevas)")


def test_todas_las_llamadas_estan_en_scope():
    """EL TEST QUE MATA LA BLOQUEANTE V1.

    Probado contra el defecto exacto del v2 (llamada en `stages["dossier"]`):
    compileall VERDE, `grep -c` SUBE a 4, este test ROJO con FUERA_DE_SCOPE=[857].
    """
    todas, en_scope = _llamadas_check_deadline()
    fuera = sorted(todas - en_scope)
    assert not fuera, (
        f"llamadas a _check_deadline FUERA de _run_pipeline_stages, en las lineas "
        f"{fuera}. _check_deadline es un closure sobre _deadline/_max_minutes/"
        "stages/started: llamarlo desde otra funcion es NameError en la primera "
        "corrida real, y compileall NO lo detecta.")
    assert todas == en_scope


def test_ninguna_clave_prohibida():
    """Ninguna clave fuera de scope aparece cerca de un _check_deadline."""
    lineas = PIPELINE.read_text(encoding="utf-8").splitlines()
    infracciones = []
    for i, l in enumerate(lineas):
        if "_check_deadline(" not in l or l.strip().startswith("def "):
            continue
        ventana = "\n".join(lineas[max(0, i - 3): i + 4])
        for clave in CLAVES_PROHIBIDAS:
            if f'stages["{clave}"]' in ventana:
                infracciones.append(f":{i + 1} -> {clave}")
    assert not infracciones, (
        f"claves de etapa PROHIBIDAS (fuera del scope del closure) a menos de 3 "
        f"lineas de un _check_deadline: {infracciones}")


@pytest.fixture()
def perf_aislado(tmp_path, monkeypatch):
    """Store de playbook_performance en tmp: cero contaminacion entre tests."""
    import playbook_performance
    monkeypatch.setattr(playbook_performance, "_PERF_DIR", tmp_path / "perf")
    playbook_performance._PERF_DIR.mkdir(parents=True, exist_ok=True)
    return playbook_performance


def test_timeout_sale_de_recomendacion(perf_aislado, monkeypatch):
    import uat_test_runner
    monkeypatch.setattr(perf_aislado, "recommend_timeout_ms", lambda *a, **kw: 150_000)
    assert uat_test_runner._resolve_timeout_ms(90_000) == 150_000


def test_sin_historial_cae_a_90000(perf_aislado):
    """SIN doble, con el store real vacio.

    Prueba que se paso `default_ms=90_000`: el default del MODULO es 120_000
    (`playbook_performance.py:160`), asi que sin ese kwarg el timeout SUBE SOLO
    de 90 s a 120 s sin que nadie lo haya decidido, y este test queda ROJO.
    """
    import uat_test_runner
    assert perf_aislado.recommend_timeout_ms(PLAYBOOK_ID) == 120_000, (
        "el default del modulo cambio; este test vigila que no se herede")
    assert uat_test_runner._resolve_timeout_ms(90_000) == 90_000


def test_nunca_baja_de_60000(perf_aislado, monkeypatch):
    """El piso del modulo evita reintroducir el fallo que motivo subir a 90 s."""
    monkeypatch.setattr(perf_aislado, "recommend_timeout_ms",
                        lambda *a, **kw: perf_aislado._TIMEOUT_FLOOR_MS)
    assert uat_timeout() >= 60_000


def uat_timeout() -> int:
    import uat_test_runner
    return uat_test_runner._resolve_timeout_ms(90_000)


def test_se_escribe_el_historial(perf_aislado):
    """EL TEST QUE MATA LA INERCIA: sin F7.2.a el store queda vacio -> ROJO."""
    import uat_test_runner
    uat_test_runner._record_run_history(duration_ms=12_345, fail_count=0, blocked_count=0)
    data = perf_aislado.get_metrics(PLAYBOOK_ID)
    assert data.get("run_count", 0) >= 1, (
        f"el store de playbook_performance quedo vacio tras la corrida: {data}. "
        "Sin escritor, recommend_timeout_ms devuelve default_ms PARA SIEMPRE.")
    assert data.get("p95_duration_ms", 0) > 0


def test_el_historial_alimenta_la_recomendacion(perf_aislado):
    """Cierra el lazo escritura->lectura de punta a punta, SIN dobles."""
    for _ in range(5):
        perf_aislado.record_run(PLAYBOOK_ID, "PASS", 200_000)
    rec = perf_aislado.recommend_timeout_ms(PLAYBOOK_ID, default_ms=90_000)
    assert rec != 90_000, (
        "con historial escrito la recomendacion tiene que dejar de ser el default; "
        f"devolvio {rec}")
    assert 60_000 <= rec <= 600_000, rec


def test_record_run_no_tumba_la_corrida(perf_aislado, monkeypatch):
    """Registrar historial NUNCA puede tumbar una corrida."""
    import uat_test_runner

    def _boom(*a, **kw):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(perf_aislado, "record_run", _boom)
    uat_test_runner._record_run_history(duration_ms=1, fail_count=0, blocked_count=0)


def test_paralelismo_sigue_cerrado():
    """Centinela de que F7.3 no se 'implemento' a medias."""
    import uat_test_runner
    assert uat_test_runner._has_per_worker_session() is False
    doc = uat_test_runner._has_per_worker_session.__doc__ or ""
    for marca in ("(a)", "(b)", "(c)"):
        assert marca in doc, (
            f"el docstring de _has_per_worker_session no declara la condicion {marca} "
            "de lo que hace falta para paralelizar")
    assert "storageState" in doc and "worker" in doc
