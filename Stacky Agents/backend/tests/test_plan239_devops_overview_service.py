"""Plan 239 F1 — services/devops_overview.py: agregación read-only del panel DevOps.

Fixtures INLINE: nada toca disco real. `now_utc` SIEMPRE inyectado (jamás datetime.now()).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import devops_overview as ov  # noqa: E402

_UTC = timezone.utc
_NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=_UTC)


def _ts(days_ago: float = 0, minutes_ago: float = 0) -> str:
    return (_NOW - timedelta(days=days_ago, minutes=minutes_ago)).isoformat()


def _deploy(app_id="app-a", target="prod", status="success", days_ago=1, action="deploy",
            finished=True):
    return {
        "app_id": app_id,
        "target": target,
        "action": action,
        "status": status,
        "started_at": _ts(days_ago),
        "finished_at": _ts(days_ago) if finished else None,
    }


def _run(project="RSPACIFICO", status="success", days_ago=1, pipeline_id="8123", minutes_ago=0):
    return {
        "project": project,
        "pipeline_id": pipeline_id,
        "ref": "main",
        "triggered_at": _ts(days_ago, minutes_ago),
        "last_status": status,
        "finished_at": _ts(days_ago, minutes_ago) if status not in ("running",) else None,
    }


# ── helpers puros ────────────────────────────────────────────────────────────

def test_parse_iso_tolerante():
    assert ov.parse_iso(None) is None
    assert ov.parse_iso("") is None
    assert ov.parse_iso("basura") is None
    assert ov.parse_iso(123) is None
    con_z = ov.parse_iso("2026-07-25T12:00:00Z")
    assert con_z is not None and con_z.tzinfo is not None
    naive = ov.parse_iso("2026-07-25T12:00:00")
    assert naive is not None and naive.tzinfo == _UTC, "naive se asume UTC"


def test_build_day_axis_14_dias():
    axis = ov.build_day_axis(_NOW, 14)
    assert len(axis) == 14
    assert axis == sorted(axis), "viejo → nuevo"
    assert axis[-1] == "2026-07-25"


def test_bucket_by_day_descarta_fuera_de_eje():
    axis = ov.build_day_axis(_NOW, 14)
    buckets = ov.bucket_by_day([_ts(1), _ts(1), _ts(40)], axis)
    assert sum(buckets) == 2, "el de hace 40 días no entra"
    assert len(buckets) == 14


# ── agregación de despliegues ────────────────────────────────────────────────

def test_aggregate_deploy_consolidado():
    """CFR sobre el TOTAL, jamás promedio de promedios.

    app A: 1 fallo / 1 deploy (CFR 1.0); app B: 0 fallos / 3 deploys (CFR 0.0).
    Consolidado correcto = 1/4 = 0.25. El promedio de promedios daría 0.5.
    """
    entries = {
        "app-a": [_deploy("app-a", status="failed", days_ago=2)],
        "app-b": [
            _deploy("app-b", status="success", days_ago=3),
            _deploy("app-b", status="success", days_ago=4),
            _deploy("app-b", status="success", days_ago=5),
        ],
    }
    agg = ov.aggregate_deploy_metrics(entries, _NOW)
    assert agg["deploys_7d"] == 4, "suma las dos apps"
    assert agg["change_failure_rate_30d"] == pytest.approx(0.25)
    assert agg["change_failure_rate_30d"] != pytest.approx(0.5)


def test_aggregate_mttr_no_cruza_apps():
    """Un fallo en A NO se 'recupera' con un éxito posterior de B."""
    entries = {
        "app-a": [_deploy("app-a", status="failed", days_ago=3)],
        "app-b": [_deploy("app-b", status="success", days_ago=1)],
    }
    agg = ov.aggregate_deploy_metrics(entries, _NOW)
    assert agg["mttr_minutes_30d"] is None


def test_aggregate_last_deploy_at_es_el_maximo():
    entries = {
        "app-a": [_deploy("app-a", days_ago=9)],
        "app-b": [_deploy("app-b", days_ago=2)],
    }
    agg = ov.aggregate_deploy_metrics(entries, _NOW)
    assert agg["last_deploy_at"] == _ts(2)


def test_aggregate_cfr_sample_se_propaga():
    entries = {"app-a": [_deploy(status="success", days_ago=i) for i in (1, 2, 3)]}
    agg = ov.aggregate_deploy_metrics(entries, _NOW)
    assert agg["cfr_sample_30d"] == 3


def test_aggregate_deploy_sin_datos():
    agg = ov.aggregate_deploy_metrics({}, _NOW)
    assert agg["change_failure_rate_30d"] is None, "NUNCA 0.0 por un dato ausente"
    assert agg["mttr_minutes_30d"] is None
    assert agg["cfr_sample_30d"] == 0


# ── agregación de CI ─────────────────────────────────────────────────────────

def test_aggregate_ci_cuenta_7d_y_fallos():
    runs = [
        _run(status="success", days_ago=1),
        _run(status="failed", days_ago=2),
        _run(status="failed", days_ago=3),
        _run(status="running", days_ago=0, minutes_ago=10),
        _run(status="success", days_ago=20),  # fuera de la ventana de 7 d
    ]
    agg = ov.aggregate_ci(runs, _NOW)
    assert agg["ci_runs_7d"] == 4
    assert agg["ci_failures_7d"] == 2
    assert agg["ci_running_now"] == 1


# ── alertas (tabla F1.2) ─────────────────────────────────────────────────────

def _alert_ids(alerts):
    return [a["id"] for a in alerts]


def _ctx(**kw):
    base = {
        "locked_targets": [],
        "last_failed_by_target": {},
        "deploy_entries": [],
        "ci_runs": [],
        "snapshot": None,
        "connections_available": True,
        "servers_available": True,
        "deploy_available": True,
        "ci_available": True,
    }
    base.update(kw)
    return base


def _kpis(**kw):
    base = {
        "deploys_7d": 0, "deploys_30d": 0, "change_failure_rate_30d": None,
        "cfr_sample_30d": 0, "mttr_minutes_30d": None, "last_deploy_at": None,
        "ci_runs_7d": 0, "ci_failures_7d": 0, "ci_running_now": 0,
        "connections_ok": None, "connections_total": None,
        "servers_total": 1, "apps_total": 1, "targets_configured": 1, "targets_locked": 0,
    }
    base.update(kw)
    return base


def test_alert_deploy_last_failed():
    ctx = _ctx(last_failed_by_target={("app-a", "prod"): _deploy(status="failed")})
    alerts = ov.derive_alerts(_kpis(), ctx, _NOW)
    a = next(x for x in alerts if x["id"] == "deploy_last_failed")
    assert a["tone"] == "danger"
    assert a["section"] == "despliegues"


def test_alert_deploy_last_failed_ignora_running():
    """Un deploy EN CURSO sobre un fallo previo no apaga ni enciende la alerta;
    un rollback exitoso posterior tampoco la apaga."""
    entries = [
        _deploy(status="failed", days_ago=3),
        _deploy(status="running", days_ago=1, finished=False),
        _deploy(status="success", days_ago=2, action="rollback"),
    ]
    last_failed = ov.last_failed_terminated_by_target({"app-a": entries})
    assert ("app-a", "prod") in last_failed, (
        "el último TERMINADO con action=deploy sigue siendo el fallido"
    )


def test_alert_deploy_last_failed_apagada_por_deploy_ok_posterior():
    entries = [
        _deploy(status="failed", days_ago=3),
        _deploy(status="success", days_ago=1),
    ]
    assert ov.last_failed_terminated_by_target({"app-a": entries}) == {}


def test_alert_deploy_failure_rate_umbral():
    assert "deploy_failure_rate" in _alert_ids(
        ov.derive_alerts(_kpis(change_failure_rate_30d=0.30, cfr_sample_30d=3), _ctx(), _NOW))
    assert "deploy_failure_rate" not in _alert_ids(
        ov.derive_alerts(_kpis(change_failure_rate_30d=0.29, cfr_sample_30d=3), _ctx(), _NOW))
    assert "deploy_failure_rate" not in _alert_ids(
        ov.derive_alerts(_kpis(change_failure_rate_30d=0.5, cfr_sample_30d=2), _ctx(), _NOW)), \
        "muestra insuficiente: 2 < CFR_MIN_SAMPLE"


def test_alert_mttr_high():
    assert "mttr_high" in _alert_ids(ov.derive_alerts(_kpis(mttr_minutes_30d=240), _ctx(), _NOW))
    assert "mttr_high" not in _alert_ids(ov.derive_alerts(_kpis(mttr_minutes_30d=239), _ctx(), _NOW))


def test_alert_deploy_stale_21_dias():
    assert "deploy_stale" in _alert_ids(
        ov.derive_alerts(_kpis(last_deploy_at=_ts(22)), _ctx(), _NOW))
    assert "deploy_stale" not in _alert_ids(
        ov.derive_alerts(_kpis(last_deploy_at=_ts(20)), _ctx(), _NOW))


def test_alert_deploy_never():
    alerts = ov.derive_alerts(_kpis(targets_configured=1, last_deploy_at=None), _ctx(), _NOW)
    a = next(x for x in alerts if x["id"] == "deploy_never")
    assert a["tone"] == "info"


def test_alert_ci_failures_dos():
    assert "ci_failures" in _alert_ids(ov.derive_alerts(_kpis(ci_failures_7d=2), _ctx(), _NOW))
    assert "ci_failures" not in _alert_ids(ov.derive_alerts(_kpis(ci_failures_7d=1), _ctx(), _NOW))


def test_alert_ci_stuck_120_min():
    trabada = _ctx(ci_runs=[_run(status="running", days_ago=0, minutes_ago=121)])
    ok = _ctx(ci_runs=[_run(status="running", days_ago=0, minutes_ago=119)])
    assert "ci_stuck" in _alert_ids(ov.derive_alerts(_kpis(), trabada, _NOW))
    assert "ci_stuck" not in _alert_ids(ov.derive_alerts(_kpis(), ok, _NOW))


def test_alert_connections_down():
    snap = {"generated_at": _ts(0), "results": [{"target": "x", "status": "fail"}],
            "summary": {"ok": 0, "warn": 0, "fail": 1, "skip": 0}}
    alerts = ov.derive_alerts(_kpis(), _ctx(snapshot=snap), _NOW)
    a = next(x for x in alerts if x["id"] == "connections_down")
    assert a["tone"] == "danger"
    assert a["section"] == "servidores"


def test_alert_connections_never_run():
    alerts = ov.derive_alerts(_kpis(), _ctx(snapshot=None), _NOW)
    a = next(x for x in alerts if x["id"] == "connections_never")
    assert a["tone"] == "info"


def test_alert_no_servers():
    alerts = ov.derive_alerts(_kpis(servers_total=0), _ctx(), _NOW)
    a = next(x for x in alerts if x["id"] == "no_servers")
    assert a["tone"] == "info"


def test_alerts_orden_danger_primero():
    snap = {"generated_at": _ts(0), "results": [{"target": "x", "status": "fail"}],
            "summary": {"ok": 0, "warn": 0, "fail": 1, "skip": 0}}
    alerts = ov.derive_alerts(_kpis(ci_failures_7d=5), _ctx(snapshot=snap), _NOW)
    assert alerts[0]["tone"] == "danger"


# ── estado global ────────────────────────────────────────────────────────────

def _blocks(deployments=True, ci=True, connections=True, servers=True, reason=None):
    return {
        "deployments": {"available": deployments, "reason": None if deployments else reason},
        "ci": {"available": ci, "reason": None if ci else reason},
        "connections": {"available": connections, "reason": None if connections else reason},
        "servers": {"available": servers, "reason": None if servers else reason},
    }


def test_status_danger_gana_a_warning():
    alerts = [{"tone": "warning"}, {"tone": "danger"}]
    assert ov.derive_status(alerts, _blocks()) == "danger"


def test_status_ok_solo_con_datos():
    assert ov.derive_status([], _blocks()) == "ok"


def test_status_unknown_sin_datos():
    """KPI-6: todos los bloques apagados ⇒ unknown, JAMÁS ok."""
    apagados = _blocks(False, False, False, False, reason="flag_off")
    assert ov.derive_status([], apagados) == "unknown"


# ── bloques honestos ─────────────────────────────────────────────────────────

def test_blocks_declare_flag_off(monkeypatch):
    """KPI-6: la flag de CI apagada se DECLARA, no se disfraza de 0."""
    import config as config_module
    monkeypatch.setattr(config_module.config, "STACKY_CI_RUN_LEDGER_ENABLED", False, raising=False)
    payload = ov.build_overview(now_utc=_NOW)
    assert payload["blocks"]["ci"]["available"] is False
    assert payload["blocks"]["ci"]["reason"] == "flag_off"


def test_block_error_lectura_no_propaga(monkeypatch):
    import config as config_module
    from services import deploy_store

    monkeypatch.setattr(config_module.config, "STACKY_DEPLOYMENTS_ENABLED", True, raising=False)

    def _boom(*a, **k):
        raise RuntimeError("disco roto")

    monkeypatch.setattr(deploy_store, "list_apps", _boom)
    payload = ov.build_overview(now_utc=_NOW)
    assert payload["blocks"]["deployments"]["available"] is False
    assert payload["blocks"]["deployments"]["reason"] == "error_lectura"
    assert "kpis" in payload, "el resto del payload sigue vivo"


# ── recent / series ──────────────────────────────────────────────────────────

def test_recent_orden_desc_y_tope_12():
    deploys = [_deploy(days_ago=i) for i in range(1, 11)]
    runs = [_run(days_ago=i, pipeline_id=str(i)) for i in range(1, 11)]
    recent = ov.build_recent(deploys, runs)
    assert len(recent) == 12
    ats = [e["at"] for e in recent]
    assert ats == sorted(ats, reverse=True)


def test_recent_mezcla_deploy_y_ci():
    recent = ov.build_recent([_deploy(days_ago=1)], [_run(days_ago=2)])
    kinds = {e["kind"] for e in recent}
    assert kinds == {"deploy", "ci"}
    secciones = {e["kind"]: e["section"] for e in recent}
    assert secciones["deploy"] == "despliegues"
    assert secciones["ci"] == "pipelines"


def test_series_cuatro_arrays_de_14(monkeypatch):
    payload = ov.build_overview(now_utc=_NOW)
    s = payload["series"]
    assert len(s["days"]) == 14
    for clave in ("deploys_by_day", "deploy_failures_by_day", "ci_runs_by_day", "ci_failures_by_day"):
        assert len(s[clave]) == 14, clave
        assert all(isinstance(v, int) for v in s[clave])


# ── Filtros (F1.2b) ──────────────────────────────────────────────────────────

def test_normalize_window_days_permitidos():
    for valido in (7, 14, 30):
        assert ov.normalize_filters(None, None, valido)["window_days"] == valido
    for invalido in (1, 999, "abc", None, -7):
        assert ov.normalize_filters(None, None, invalido)["window_days"] == ov.SERIES_DAYS


def test_normalize_app_id_inexistente_se_descarta():
    f = ov.normalize_filters("no-existe", None, 14, valid_apps={"app-a"}, valid_projects=set())
    assert f["app_id"] is None


def test_normalize_recorta_y_topea():
    f = ov.normalize_filters(" app-a ", None, 14, valid_apps={"app-a"}, valid_projects=set())
    assert f["app_id"] == "app-a"
    largo = ov.normalize_filters("x" * 300, None, 14, valid_apps=None, valid_projects=None)
    assert largo["app_id"] is None


def _wire(monkeypatch, apps=None, ledger=None, runs=None, servers=None, snapshot=None):
    """Cablea las 4 fuentes con fixtures inline (cero disco)."""
    import config as config_module
    from services import deploy_store, ci_run_ledger, server_registry
    import api.devops_connections as conns

    for flag in ("STACKY_DEPLOYMENTS_ENABLED", "STACKY_CI_RUN_LEDGER_ENABLED",
                 "STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED", "STACKY_DEVOPS_SERVERS_ENABLED"):
        monkeypatch.setattr(config_module.config, flag, True, raising=False)

    ledger = ledger or {}
    monkeypatch.setattr(deploy_store, "list_apps", lambda: apps or [])
    monkeypatch.setattr(deploy_store, "read_ledger",
                        lambda app_id=None, target=None, limit=100: list(ledger.get(app_id, [])))
    monkeypatch.setattr(deploy_store, "is_locked", lambda app_id, target=None: False)
    monkeypatch.setattr(ci_run_ledger, "list_runs", lambda project=None, limit=50: list(runs or []))
    monkeypatch.setattr(server_registry, "list_servers", lambda: servers or [])
    monkeypatch.setattr(conns, "get_snapshot", lambda: snapshot)


_APPS = [
    {"id": "app-a", "name": "App A", "targets": {"prod": {}}},
    {"id": "app-b", "name": "App B", "targets": {"prod": {}}},
]


def test_filtro_app_id_recorta_kpis(monkeypatch):
    _wire(monkeypatch, apps=_APPS, ledger={
        "app-a": [_deploy("app-a", days_ago=1)],
        "app-b": [_deploy("app-b", days_ago=1), _deploy("app-b", days_ago=2)],
    })
    todos = ov.build_overview(now_utc=_NOW)
    solo_a = ov.build_overview(now_utc=_NOW, app_id="app-a")
    assert todos["kpis"]["deploys_7d"] == 3
    assert solo_a["kpis"]["deploys_7d"] == 1
    assert solo_a["filters"]["app_id"] == "app-a"


def test_filtro_project_recorta_ci(monkeypatch):
    _wire(monkeypatch, runs=[
        _run(project="P1", days_ago=1, pipeline_id="1"),
        _run(project="P2", days_ago=1, pipeline_id="2"),
        _run(project="P2", days_ago=2, pipeline_id="3"),
    ])
    todos = ov.build_overview(now_utc=_NOW)
    solo_p2 = ov.build_overview(now_utc=_NOW, project="P2")
    assert todos["kpis"]["ci_runs_7d"] == 3
    assert solo_p2["kpis"]["ci_runs_7d"] == 2
    assert solo_p2["filters"]["project"] == "P2"


def test_filtro_recorta_recent_y_alertas(monkeypatch):
    _wire(monkeypatch, apps=_APPS, ledger={
        "app-a": [_deploy("app-a", status="failed", days_ago=1)],
        "app-b": [_deploy("app-b", status="success", days_ago=1)],
    })
    solo_b = ov.build_overview(now_utc=_NOW, app_id="app-b")
    assert "deploy_last_failed" not in [a["id"] for a in solo_b["alerts"]], \
        "la alerta de una app filtrada fuera no puede aparecer"
    assert all(e.get("app_id") in (None, "app-b") for e in solo_b["recent"])


def test_options_no_se_recorta_con_el_filtro(monkeypatch):
    _wire(monkeypatch, apps=_APPS, ledger={
        "app-a": [_deploy("app-a", days_ago=1)],
        "app-b": [_deploy("app-b", days_ago=1)],
    })
    solo_a = ov.build_overview(now_utc=_NOW, app_id="app-a")
    assert len(solo_a["options"]["apps"]) == 2, "si se recortara no se podría volver a 'todas'"


def test_window_days_30_da_series_de_30(monkeypatch):
    payload = ov.build_overview(now_utc=_NOW, window_days=30)
    assert len(payload["series"]["days"]) == 30
    for clave in ("deploys_by_day", "deploy_failures_by_day", "ci_runs_by_day", "ci_failures_by_day"):
        assert len(payload["series"][clave]) == 30


def test_filters_es_eco_de_lo_APLICADO(monkeypatch):
    _wire(monkeypatch, apps=_APPS)
    payload = ov.build_overview(now_utc=_NOW, app_id="no-existe")
    assert payload["filters"]["app_id"] is None, "el eco es de lo aplicado, no de lo pedido"


# ── pureza (KPI-7 a nivel módulo) ────────────────────────────────────────────

def test_overview_no_importa_red_ni_remoto():
    import ast
    src = Path(ov.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    prohibidos = {"requests", "subprocess", "socket", "http", "urllib", "winrm"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & prohibidos), f"devops_overview abre red/procesos: {imported & prohibidos}"
    assert "remote_exec" not in src, "el overview NO ejecuta comandos remotos"
    assert "run_connection_check" not in src, "el overview NO dispara el doctor (HITL plan 116)"
