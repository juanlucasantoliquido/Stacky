"""Plan 120 F1 — deploy_planner.py, motor 100% puro (sin I/O)."""
from __future__ import annotations

import ast
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import deploy_planner as dp

_UTC = timezone.utc


def _app(**overrides):
    base = {
        "id": "miapp",
        "artifact": {"kind": "folder", "path": "C:\\build\\miapp\\out"},
        "targets": {
            "__local__": {
                "install_path": "D:\\apps\\miapp",
                "smoke": {"kind": "http", "url": "http://localhost:8080/health", "command": None},
                "pre_switch": None,
                "post_switch": None,
                "protected": False,
            },
        },
    }
    base.update(overrides)
    return base


# ── validate_app ─────────────────────────────────────────────────────────────

def test_validate_app_casos():
    assert dp.validate_app(_app()) == []

    bad_id = dp.validate_app(_app(id="Mi App!"))
    assert any("id" in e for e in bad_id)

    bad_kind = _app()
    bad_kind["artifact"] = {"kind": "exe", "path": "C:\\x"}
    assert any("artifact.kind" in e for e in dp.validate_app(bad_kind))

    bad_path = _app()
    bad_path["artifact"] = {"kind": "folder", "path": "relative\\path"}
    assert any("artifact.path" in e for e in dp.validate_app(bad_path))


def test_make_version_id_determinista():
    now = datetime(2026, 7, 10, 15, 30, 0, tzinfo=_UTC)
    vid = dp.make_version_id(now, "ab12cd34ef56")
    assert vid == "20260710-153000-ab12cd34"


# ── build_deploy_plan / build_rollback_plan ─────────────────────────────────

def test_deploy_plan_orden_y_pasos():
    app = _app()
    target_cfg = dict(app["targets"]["__local__"])
    target_cfg["pre_switch"] = "Stop-Service miapp"
    target_cfg["post_switch"] = "Start-Service miapp"
    plan = dp.build_deploy_plan(app, "__local__", target_cfg, "20260710-153000-ab12cd34", 3, 30)
    names = [s["name"] for s in plan]
    assert names == [
        "preflight", "ensure_dirs", "transfer", "unpack", "pre_switch", "switch",
        "write_marker", "post_switch", "smoke", "prune", "cleanup",
    ]


def test_deploy_plan_omite_hooks_y_smoke_none():
    app = _app()
    target_cfg = dict(app["targets"]["__local__"])
    target_cfg["smoke"] = {"kind": "none", "url": None, "command": None}
    plan = dp.build_deploy_plan(app, "__local__", target_cfg, "20260710-153000-ab12cd34", 3, 30)
    names = [s["name"] for s in plan]
    assert "pre_switch" not in names
    assert "post_switch" not in names
    assert "smoke" not in names


def test_deploy_plan_housekeeping_solo_prune_y_cleanup():
    app = _app()
    target_cfg = dict(app["targets"]["__local__"])
    plan = dp.build_deploy_plan(app, "__local__", target_cfg, "20260710-153000-ab12cd34", 3, 30)
    housekeeping_names = {s["name"] for s in plan if s["housekeeping"]}
    assert housekeeping_names == {"prune", "cleanup"}


def test_rollback_plan_has_no_transfer():
    app = _app()
    target_cfg = dict(app["targets"]["__local__"])
    plan = dp.build_rollback_plan(app, "__local__", target_cfg, "20260709-101500-99ffee11", 30)
    names = [s["name"] for s in plan]
    assert "transfer" not in names
    assert "unpack" not in names
    assert names[0] == "switch"


# ── comandos exactos ─────────────────────────────────────────────────────────

def test_switch_commands_exactos():
    cmds = dp.build_switch_commands("D:\\apps\\miapp", "20260710-153000-ab12cd34")
    assert cmds == [
        'cmd /c if exist "D:\\apps\\miapp\\current" rmdir "D:\\apps\\miapp\\current"',
        'cmd /c mklink /J "D:\\apps\\miapp\\current" "D:\\apps\\miapp\\releases\\20260710-153000-ab12cd34"',
    ]


def test_switch_commands_primer_deploy():
    # C1 v2: SIEMPRE lleva `if exist` (no-op si `current` no existe aún) —
    # así el PRIMER deploy contra un install_path virgen no revienta.
    cmds = dp.build_switch_commands("D:\\apps\\miapp", "v1")
    assert "if exist" in cmds[0]


def test_switch_commands_rechaza_comillas():
    import pytest
    with pytest.raises(ValueError):
        dp.build_switch_commands('D:\\apps\\mi"app', "v1")


def test_marker_command_exacto_y_valida_comillas():
    cmd = dp.build_marker_command("D:\\apps\\miapp", {"version_id": "v1", "app_id": "miapp"})
    assert cmd.startswith("Set-Content -LiteralPath 'D:\\apps\\miapp\\release.json' -Value '")
    assert cmd.endswith("' -Encoding utf8")
    import pytest
    with pytest.raises(ValueError):
        dp.build_marker_command("D:\\apps\\miapp", {"version_id": "it's-bad"})


def test_parse_smoke_http_stdout():
    assert dp.parse_smoke_http_stdout("algo 200 mas") == 200
    assert dp.parse_smoke_http_stdout("404") == 404
    assert dp.parse_smoke_http_stdout("ERR: no se pudo conectar") is None
    assert dp.parse_smoke_http_stdout("") is None


# ── retención ─────────────────────────────────────────────────────────────────

def test_prune_nunca_current():
    existing = ["20260701-000000-aa", "20260702-000000-bb", "20260703-000000-cc", "20260704-000000-dd"]
    to_delete = dp.prune_versions(existing, retain=2, current="20260701-000000-aa")
    assert "20260701-000000-aa" not in to_delete
    assert set(to_delete) == {"20260702-000000-bb"}


# ── drift / marker ─────────────────────────────────────────────────────────────

def test_compute_drift_4_estados():
    assert dp.compute_drift(None, None) == "never"
    assert dp.compute_drift("v1", None) == "unknown"
    assert dp.compute_drift("v1", {"version_id": "v1"}) == "ok"
    assert dp.compute_drift("v1", {"version_id": "v2"}) == "drift"


def test_parse_release_marker_corrupto():
    assert dp.parse_release_marker("{not json") is None
    assert dp.parse_release_marker("") is None
    assert dp.parse_release_marker('{"version_id":"v1"}') == {"version_id": "v1"}


# ── DORA ─────────────────────────────────────────────────────────────────────

def test_dora_metrics_fixture():
    now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=_UTC)

    def _ts(days_ago, hour=12):
        return (now - timedelta(days=days_ago)).isoformat()

    entries = [
        {"action": "deploy", "status": "success", "finished_at": _ts(20)},
        {"action": "deploy", "status": "failed", "finished_at": _ts(10)},
        {"action": "deploy", "status": "success", "finished_at": _ts(9)},  # recovery
        {"action": "deploy", "status": "success", "finished_at": _ts(3)},
        {"action": "deploy", "status": "success", "finished_at": _ts(1)},
        {"action": "rollback", "status": "success", "finished_at": _ts(1)},  # ignorado (no es deploy)
    ]
    metrics = dp.dora_metrics(entries, now)
    assert metrics["deploys_30d"] == 5
    assert metrics["deploys_7d"] == 2
    assert 0 < metrics["change_failure_rate_30d"] < 1
    assert metrics["mttr_minutes_30d"] is not None
    assert metrics["mttr_minutes_30d"] > 0
    assert metrics["last_deploy_at"] == _ts(1)


def test_dora_metrics_vacio_sin_division_por_cero():
    now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=_UTC)
    metrics = dp.dora_metrics([], now)
    assert metrics["deploys_7d"] == 0
    assert metrics["deploys_30d"] == 0
    assert metrics["change_failure_rate_30d"] is None
    assert metrics["mttr_minutes_30d"] is None
    assert metrics["last_deploy_at"] is None


# ── A1 / A2 [ADICIÓN ARQUITECTO] ────────────────────────────────────────────

def test_derive_effective_status_stale_y_passthrough():
    now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=_UTC)
    fresh = {"status": "running", "started_at": (now - timedelta(minutes=5)).isoformat()}
    assert dp.derive_effective_status(fresh, now) == "running"

    stale = {"status": "running", "started_at": (now - timedelta(hours=2)).isoformat()}
    assert dp.derive_effective_status(stale, now, stale_after_s=3600) == "stale"

    other = {"status": "success", "started_at": (now - timedelta(hours=5)).isoformat()}
    assert dp.derive_effective_status(other, now) == "success"


def test_check_disk_headroom():
    assert dp.check_disk_headroom(None, 100) is None  # desconocido: no bloquea, sin warning
    assert dp.check_disk_headroom(1000, 100) is None  # 10x libre: sobra
    warning = dp.check_disk_headroom(50, 100)  # menos de 2x
    assert warning is not None
    assert "Espacio libre" in warning


# ── pureza ────────────────────────────────────────────────────────────────────

def test_planner_es_puro():
    src = Path(dp.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"requests", "subprocess", "flask"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & banned), f"deploy_planner.py importa módulos con I/O: {imported & banned}"
