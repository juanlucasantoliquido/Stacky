"""Plan 214 F2 — detección temprana de desvío de navegación (NAV_DEVIATION).

El circuito completo que se prueba acá:
  assert_arrival (DOM/URL)  →  NavigationResult error_code NAV_DEVIATION
      →  _classify_error                    (contrato del driver)
      →  replan_engine switch_human_path    (replan acotado)
      →  stages.runner.nav_deviations       (telemetría del pipeline)
      →  huella qa_uat_nav_deviation        (catálogo de regresiones)

Los controles NEGATIVOS son los que importan: no alcanza con probar el camino
que ya funciona, hay que probar el que DEBE fallar.

Comando:
  cd "N:\\GIT\\RS\\STACKY\\Stacky\\Stacky tools\\QA UAT Agent"
  & "..\\..\\Stacky Agents\\backend\\.venv\\Scripts\\python.exe" -m pytest tests\\unit\\test_plan214_nav_deviation.py -q
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_TOOL = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, _TOOL)

import replan_engine
from navigation_driver import NavigationDriver, _classify_error


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ui_map(tmp_path: Path, screen: str, anchor: str) -> Path:
    d = tmp_path / "ui_maps"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{screen}.json").write_text(json.dumps({
        "ok": True, "screen": screen,
        "elements": [{"kind": "button", "asp_id": anchor, "label": "Guardar"}],
    }), encoding="utf-8")
    return d


def _page(url: str, locator_count: int = 0) -> MagicMock:
    page = MagicMock()
    page.url = url
    loc = MagicMock()
    loc.count = AsyncMock(return_value=locator_count)
    page.locator = MagicMock(return_value=loc)
    page.evaluate = AsyncMock(return_value=True)
    page.wait_for_url = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.screenshot = AsyncMock()
    return page


# ── assert_arrival ────────────────────────────────────────────────────────────

def test_assert_arrival_por_ui_map(tmp_path):
    """Llegada válida: el ancla del ui_map está presente en el DOM."""
    d = _ui_map(tmp_path, "FrmDetalleClie.aspx", "btnGuardar")
    page = _page("http://localhost/AgendaWeb/FrmDetalleClie.aspx", locator_count=1)
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    res = asyncio.run(driver.assert_arrival("FrmDetalleClie.aspx", ui_maps_dir=d))

    assert res["ok"] is True
    assert res["deviation"] is None
    assert res["checked_by"] == "ui_map"
    page.locator.assert_called_with("#btnGuardar")


def test_assert_arrival_desvio(tmp_path):
    """Desvío duro: ni el ancla ni la URL corresponden a la pantalla esperada."""
    d = _ui_map(tmp_path, "FrmDetalleClie.aspx", "btnGuardar")
    page = _page("http://localhost/AgendaWeb/FrmAgenda.aspx", locator_count=0)
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    res = asyncio.run(driver.assert_arrival("FrmDetalleClie.aspx", ui_maps_dir=d))

    assert res["ok"] is False
    assert "expected=FrmDetalleClie.aspx" in res["deviation"]
    assert "FrmAgenda.aspx" in res["deviation"]


def test_assert_arrival_url_ok_pero_pantalla_no_cargo(tmp_path):
    """CONTROL DISCRIMINANTE: la URL miente, el DOM no.

    Es el caso que un chequeo por URL deja pasar (falso PASS) y el único que
    justifica el ui_map: llegamos a la URL correcta pero la pantalla no cargó.
    """
    d = _ui_map(tmp_path, "FrmDetalleClie.aspx", "btnGuardar")
    page = _page("http://localhost/AgendaWeb/FrmDetalleClie.aspx", locator_count=0)
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    res = asyncio.run(driver.assert_arrival("FrmDetalleClie.aspx", ui_maps_dir=d))

    assert res["ok"] is False, "un ancla ausente con la URL correcta DEBE ser desvío"
    assert res["checked_by"] == "ui_map"


def test_assert_arrival_sin_ui_map_degrada_a_url(tmp_path):
    """Sin ui_map el criterio es la URL — equivalente al comportamiento previo."""
    page = _page("http://localhost/AgendaWeb/FrmDetalleClie.aspx", locator_count=0)
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    ok = asyncio.run(driver.assert_arrival("FrmDetalleClie.aspx", ui_maps_dir=tmp_path / "vacio"))
    ko = asyncio.run(driver.assert_arrival("FrmJDemanda.aspx", ui_maps_dir=tmp_path / "vacio"))

    assert ok["ok"] is True and ok["checked_by"] == "url"
    assert ko["ok"] is False and ko["checked_by"] == "url"


def test_assert_arrival_locator_roto_no_lanza(tmp_path):
    """Ante un locator inutilizable degrada a URL en vez de propagar."""
    d = _ui_map(tmp_path, "FrmDetalleClie.aspx", "btnGuardar")
    page = _page("http://localhost/AgendaWeb/FrmDetalleClie.aspx")
    page.locator = MagicMock(side_effect=RuntimeError("page closed"))
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    res = asyncio.run(driver.assert_arrival("FrmDetalleClie.aspx", ui_maps_dir=d))
    assert res["ok"] is True
    assert res["checked_by"] == "url"


# ── Cableado real en _execute_nav (anti-inerte) ───────────────────────────────

def test_execute_nav_emite_nav_deviation(tmp_path):
    """El desvío NO es un método suelto: _execute_nav lo devuelve como resultado."""
    d = _ui_map(tmp_path, "FrmDetalleClie.aspx", "btnGuardar")
    page = _page("http://localhost/AgendaWeb/FrmAgenda.aspx", locator_count=0)
    driver = NavigationDriver(page, evidence_dir=tmp_path)
    driver.ui_maps_dir = d

    res = asyncio.run(driver.via_form_submit(
        eventtarget="ctl00$c$Grid", eventargument="Select$0",
        wait_url_contains="FrmDetalleClie", timeout_ms=500, retries=1,
        expected_screen="FrmDetalleClie.aspx",
    ))

    assert res.ok is False
    assert res.error_code == "NAV_DEVIATION"
    assert "NAV_DEVIATION:" in res.error_detail
    assert "expected=FrmDetalleClie.aspx" in res.error_detail


def test_execute_nav_sin_expected_screen_es_byte_identico(tmp_path):
    """KPI-6: sin expected_screen el driver se comporta EXACTO como antes."""
    page = _page("http://localhost/AgendaWeb/FrmAgenda.aspx", locator_count=0)
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    res = asyncio.run(driver.via_form_submit(
        eventtarget="ctl00$c$Grid", eventargument="Select$0",
        wait_url_contains="FrmDetalleClie", timeout_ms=500, retries=1,
    ))

    assert res.ok is True
    assert res.error_code is None


def test_via_link_click_usa_no_wait_after(tmp_path):
    """El click de link va con no_wait_after (patrón WebForms-safe)."""
    page = _page("http://localhost/AgendaWeb/FrmDetalleClie.aspx", locator_count=1)
    loc = page.locator.return_value
    loc.scroll_into_view_if_needed = AsyncMock()
    loc.click = AsyncMock()
    driver = NavigationDriver(page, evidence_dir=tmp_path)

    res = asyncio.run(driver.via_link_click("#lnk", "FrmDetalleClie", timeout_ms=500, retries=1))

    assert res.ok is True
    assert loc.click.await_args.kwargs.get("no_wait_after") is True
    assert page.evaluate.await_count >= 1, "debe haber esperado el idle de ASP.NET"


# ── _classify_error ───────────────────────────────────────────────────────────

def test_classify_error_nav_deviation():
    assert _classify_error(
        "NAV_DEVIATION: expected=FrmDetalleClie.aspx url=http://x/FrmAgenda.aspx",
        "http://x/FrmAgenda.aspx",
    ) == "NAV_DEVIATION"


def test_classify_error_no_pisa_las_ramas_previas():
    """Control negativo: NAV_DEVIATION no debe canibalizar otras clases."""
    assert _classify_error("NAV_SESSION_LOST: expulsado", "http://x/FrmLogin.aspx") == "NAV_SESSION_LOST"
    assert _classify_error("Timeout 30000ms exceeded", "http://x/FrmAgenda.aspx") == "NAV_TIMEOUT"


# ── replan_engine ─────────────────────────────────────────────────────────────

_CONTRACTS_2 = """
FrmDetalleClie.aspx:
  screen_type: detail
  human_paths:
    open_from_busqueda:
      entrypoint: FrmBusqueda.aspx
    open_from_agenda:
      entrypoint: FrmAgenda.aspx
"""

_CONTRACTS_1 = """
FrmDetalleClie.aspx:
  screen_type: detail
  human_paths:
    open_from_busqueda:
      entrypoint: FrmBusqueda.aspx
"""


def _failure() -> dict:
    return {
        "scenario_id": "SC-01",
        "runner_reason": "",
        "error_message": "NAV_DEVIATION: expected=FrmDetalleClie.aspx url=http://x/FrmAgenda.aspx",
        "console_errors": [],
        "screen_errors": [],
        "assertion_failures": [],
    }


def test_replan_switch_human_path(tmp_path, monkeypatch):
    """Con un human_path alternativo sin intentar, el replan lo elige."""
    contracts = tmp_path / "navigation_contracts.yml"
    contracts.write_text(_CONTRACTS_2, encoding="utf-8")
    monkeypatch.setattr(replan_engine, "_CONTRACTS_PATH", contracts)

    spec: dict = {"test_cases": [{"id": "SC-01", "navigation_path": ["viejo"]}]}
    decision = replan_engine._classify_failure(_failure(), spec, tmp_path)

    assert decision is not None
    assert decision.replan_type == "switch_human_path"
    assert decision.patch["human_path"] == "open_from_agenda"
    assert decision.patch["screen"] == "FrmDetalleClie.aspx"

    replan_engine._apply_patch(decision, spec)
    meta = spec["_replan_meta"]
    assert meta["preferred_human_path"]["FrmDetalleClie.aspx"] == "open_from_agenda"
    assert meta["tried_human_paths"]["FrmDetalleClie.aspx"] == [
        "open_from_busqueda", "open_from_agenda"]
    assert "navigation_path" not in spec["test_cases"][0]


def test_replan_sin_alternativa_escala(tmp_path, monkeypatch):
    """CONTROL NEGATIVO: con UN solo human_path no hay alternativa → escalate.

    Si esto devolviera switch_human_path el replan gastaría sus 3 rondas
    reintentando el MISMO camino y terminaría en un FAIL mudo.
    """
    contracts = tmp_path / "navigation_contracts.yml"
    contracts.write_text(_CONTRACTS_1, encoding="utf-8")
    monkeypatch.setattr(replan_engine, "_CONTRACTS_PATH", contracts)

    spec: dict = {"test_cases": [{"id": "SC-01"}]}
    decision = replan_engine._classify_failure(_failure(), spec, tmp_path)

    assert decision is not None
    assert decision.replan_type == "escalate"
    assert "NAV_DEVIATION" in decision.description


def test_replan_nav_deviation_manda_sobre_las_genericas(tmp_path, monkeypatch):
    """El texto del desvío trae 'timeout'; igual debe clasificarse como NAV."""
    contracts = tmp_path / "navigation_contracts.yml"
    contracts.write_text(_CONTRACTS_2, encoding="utf-8")
    monkeypatch.setattr(replan_engine, "_CONTRACTS_PATH", contracts)

    f = _failure()
    f["runner_status"] = "blocked"
    f["error_message"] += " (timeout exceeded)"
    decision = replan_engine._classify_failure(f, {"test_cases": []}, tmp_path)

    assert decision.replan_type == "switch_human_path"


def test_replan_analyze_reintenta_con_el_camino_nuevo(tmp_path, monkeypatch):
    """Integración: analyze() convierte el desvío en action='retry'."""
    contracts = tmp_path / "navigation_contracts.yml"
    contracts.write_text(_CONTRACTS_2, encoding="utf-8")
    monkeypatch.setattr(replan_engine, "_CONTRACTS_PATH", contracts)

    runner_output = {
        "ok": True, "total": 1, "pass": 0, "fail": 1, "blocked": 0,
        "runs": [{
            "scenario_id": "SC-01", "spec_file": "s.spec.ts", "status": "fail",
            "duration_ms": 10,
            "assertion_failures": [{
                "message": "NAV_DEVIATION: expected=FrmDetalleClie.aspx url=http://x/FrmAgenda.aspx"}],
        }],
    }
    result = replan_engine.analyze(
        runner_output, None, {"test_cases": [{"id": "SC-01"}]}, tmp_path,
        round_number=1, dry_run=True)

    assert result.action == "retry"
    assert result.decisions[0].replan_type == "switch_human_path"


# ── Telemetría del pipeline ───────────────────────────────────────────────────

def test_pipeline_cuenta_nav_deviations():
    import qa_uat_pipeline

    runner = {
        "ok": True, "pass": 1, "fail": 1, "blocked": 0, "total": 2,
        "runs": [
            {"scenario_id": "SC-01", "status": "pass"},
            {"scenario_id": "SC-02", "status": "fail",
             "assertion_failures": [{"message": "NAV_DEVIATION: expected=X url=Y"}]},
        ],
    }
    assert qa_uat_pipeline._count_nav_deviations(runner) == 1
    assert qa_uat_pipeline._summarise_runner(runner)["nav_deviations"] == 1


def test_nav_deviations_presente_incluso_si_el_runner_fallo():
    """KPI-1: el contador se expone en el 100% de los runs, no solo en los ok."""
    import qa_uat_pipeline
    roto = {"ok": False, "error": "RUNNER_CRASH", "message": "boom"}
    assert qa_uat_pipeline._summarise_runner(roto)["nav_deviations"] == 0


def test_count_nav_deviations_no_lanza_con_basura():
    import qa_uat_pipeline
    for basura in (None, {}, {"runs": None}, {"runs": [None, 3, "x"]}):
        assert qa_uat_pipeline._count_nav_deviations(basura) == 0


# ── Template de specs y catálogo de huellas ──────────────────────────────────

def test_template_contiene_helper():
    tpl = (Path(_TOOL) / "templates" / "playwright_test.spec.ts.j2").read_text(encoding="utf-8")
    assert tpl.count("waitForAspNetIdle") >= 2, "definición + al menos un uso"
    assert "noWaitAfter: true" in tpl
    assert "NAV_DEVIATION" in tpl, "el spec generado debe emitir la huella del desvío"


def test_huella_nav_deviation_sembrada():
    catalog = (Path(_TOOL).parent.parent / "Stacky Agents" / "docs" / "sistema"
               / "error_fingerprints.json")
    data = json.loads(catalog.read_text(encoding="utf-8"))
    fp = next((f for f in data["fingerprints"] if f["id"] == "qa_uat_nav_deviation"), None)
    assert fp is not None
    assert fp["log_pattern"] == "NAV_DEVIATION"
    import re
    for sample in fp["self_test"]["matches"]:
        assert re.search(fp["log_pattern"], sample)
    for sample in fp["self_test"]["clean"]:
        assert not re.search(fp["log_pattern"], sample)
