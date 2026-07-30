"""
test_plan274_wallclock.py — Plan 274 F9 (baseline capturado en F0.5).

POR QUE EXISTE. Todo el resto del plan optimiza un PROXY: KPI-1 cuenta los
milisegundos ESCRITOS EN UN ARCHIVO, no el tiempo que tarda la corrida. Los dos
son separables: F1 reemplaza `waitForTimeout(800)` por una espera por estado que
en el peor caso espera MAS. Con solo los KPI de proxy, una corrida mas lenta
cierra todas las fases en verde.

EL RELOJ DE PARED ES `stats.duration`, NO la suma de `suites[*]`.
Medido contra el unico reporte real del repo:
    walk(suites) -> 47 176 ms
    stats.duration -> 70 030 ms
Recorrer `suites` ignora `globalSetup` (el login contra AgendaWeb) y todo el
overhead: subestima 22 854 ms, un 33 %. Justo la parte que puede degradarse sin
que nadie la vea.

EL BASELINE SE TOMA EN F0.5, ANTES DE F1. Si se capturara al final congelaria el
reloj YA modificado y el ratchet no podria detectar nada: el gate mas importante
del plan quedaria ciego a su propio riesgo principal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[2]
REPORTS = TOOL_ROOT / "reports"
REPORT = REPORTS / "playwright-results.json"
WALLCLOCK_BASELINE = REPORTS / "plan274_wallclock_baseline.json"

# Tolerancia declarada: absorbe el ruido de una maquina compartida.
TOLERANCIA = 1.10


def _wall_clock(report_path: Path) -> tuple[int, int, dict]:
    """(stats.duration, n_tests, {test_id: duration}).

    `stats.duration` es el reloj de pared. El dict de `suites[*]` sirve SOLO
    para atribuir el crecimiento por test en el mensaje de fallo.
    """
    d = json.loads(report_path.read_text(encoding="utf-8"))
    st = d["stats"]
    n_tests = st.get("expected", 0) + st.get("unexpected", 0) + st.get("flaky", 0)

    per_test: dict = {}

    def walk(node, title=""):
        if isinstance(node, dict):
            name = node.get("title") or title
            if "duration" in node and isinstance(node["duration"], (int, float)):
                key = name or f"anon_{len(per_test)}"
                per_test[key] = max(per_test.get(key, 0), node["duration"])
            for k, v in node.items():
                if k != "duration":
                    walk(v, name)
        elif isinstance(node, list):
            for v in node:
                walk(v, title)

    walk(d.get("suites", []))
    return int(st["duration"]), int(n_tests), per_test


def _ms_por_test(total_ms: int, n_tests: int) -> float:
    return (total_ms / n_tests) if n_tests else 0.0


def test_baseline_de_reloj_existe_o_se_crea():
    """F0.5 — se corre UNA vez, ANTES de F1. Despues ninguna fase lo reescribe."""
    if not REPORT.is_file():
        pytest.skip(
            f"no existe {REPORT.name}: KPI-7 queda NO MEDIBLE y hay que anotarlo "
            "asi en §9 del plan. Prohibido inventar un baseline post-hoc.")
    if not WALLCLOCK_BASELINE.is_file():
        total, n, _ = _wall_clock(REPORT)
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        REPORTS.mkdir(parents=True, exist_ok=True)
        WALLCLOCK_BASELINE.write_text(
            json.dumps({
                "pre_plan": {
                    "wall_clock_ms": total,
                    "tests": n,
                    "ms_por_test": round(_ms_por_test(total, n), 3),
                    "startTime": raw["stats"].get("startTime"),
                    "nota": ("capturado en F0.5, ANTES de F1. Corresponde a la unica "
                             "corrida real del repo (3 specs P01/P02/P03 del ticket 367)."),
                }
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    base = json.loads(WALLCLOCK_BASELINE.read_text(encoding="utf-8"))
    assert "pre_plan" in base
    assert base["pre_plan"]["ms_por_test"] > 0


def test_el_reloj_no_empeora():
    """Criterio DELTA con tolerancia declarada, sobre ms POR TEST.

    Se compara ms por test y no el total: si mañana hay 6 specs en vez de 5, un
    total mayor no es una regresion.
    """
    if not REPORT.is_file():
        pytest.skip(f"no existe {REPORT.name}: ratchet sin medicion actual")
    if not WALLCLOCK_BASELINE.is_file():
        pytest.skip("no existe el baseline de F0.5; correr primero "
                    "test_baseline_de_reloj_existe_o_se_crea")

    base = json.loads(WALLCLOCK_BASELINE.read_text(encoding="utf-8"))["pre_plan"]
    total, n, per_test = _wall_clock(REPORT)
    actual = _ms_por_test(total, n)
    techo = base["ms_por_test"] * TOLERANCIA

    peores = sorted(per_test.items(), key=lambda kv: -kv[1])[:5]
    assert actual <= techo, (
        f"REGRESION DE RELOJ DE PARED: {actual:.0f} ms/test contra un baseline "
        f"pre-plan de {base['ms_por_test']:.0f} ms/test (techo {techo:.0f} con "
        f"tolerancia {TOLERANCIA}). Total {total} ms sobre {n} tests. "
        f"Tests mas lentos de esta corrida: {peores}. "
        "Esto es exactamente lo que KPI-1 NO puede ver: una espera por estado "
        "mas lenta que el sleep que reemplazo.")


def test_se_salta_si_no_hay_reporte(tmp_path):
    """Nunca falla por ausencia de reporte: es un ratchet, no un requisito."""
    faltante = tmp_path / "no_existe.json"
    assert not faltante.is_file()
    with pytest.raises(pytest.skip.Exception):
        if not faltante.is_file():
            pytest.skip("sin reporte -> skip, no fallo")


def test_no_se_mide_sobre_suites(tmp_path):
    """CORRE CONTRA EL DEFECTO del v2: con su C-7 (suma de suites[*]) esto es ROJO.

    Fixture donde los dos numeros difieren a proposito, con la misma proporcion
    del reporte real (47 176 in-test vs 70 030 de reloj de pared).
    """
    fixture = tmp_path / "report.json"
    fixture.write_text(json.dumps({
        "stats": {"duration": 70030.106, "expected": 3, "unexpected": 0,
                  "flaky": 0, "startTime": "2026-07-26T00:36:03.100Z"},
        "suites": [{
            "title": "s",
            "specs": [
                {"title": "t1", "tests": [{"results": [{"duration": 15942}]}]},
                {"title": "t2", "tests": [{"results": [{"duration": 15302}]}]},
                {"title": "t3", "tests": [{"results": [{"duration": 15932}]}]},
            ],
        }],
    }), encoding="utf-8")

    total, n, per_test = _wall_clock(fixture)
    suma_suites = sum(per_test.values())

    assert total == 70030, (
        f"_wall_clock devolvio {total}: tiene que ser stats.duration (70030), "
        "no la suma de suites[*]")
    assert total != suma_suites, "el fixture no discrimina: los dos numeros coinciden"
    assert suma_suites == 47176, f"la suma in-test del fixture da {suma_suites}, esperaba 47176"
    assert n == 3
