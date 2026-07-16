"""Plan 120 F4 — deploy_executor.py: transportes Local/WinRM, smoke, artefacto,
orquestación async. Todo con FakeTransport / tmp_path — CERO red real."""
from __future__ import annotations

import os
import sys
import threading as _threading_mod
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services import deploy_executor as ex
from services import deploy_store as store


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def flags_on(monkeypatch):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_DEPLOYMENTS_ENABLED", True, raising=False)
    monkeypatch.setattr(_config.config, "STACKY_DEPLOYMENTS_EXECUTE_ENABLED", True, raising=False)
    return _config.config


@pytest.fixture()
def st(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_apps_path", lambda: tmp_path / "deploy_apps.json")
    monkeypatch.setattr(store, "_ledger_path", lambda: tmp_path / "deploy_ledger.jsonl")
    store._RUN_LOCKS.clear()
    return store


@pytest.fixture()
def synchronous_thread(monkeypatch):
    """Reemplaza threading.Thread por una versión que corre `target()`
    SINCRÓNICAMENTE en start() — determinismo para verificar orden/():
    sigue siendo "un solo thread por orden" (F4), solo que sin paralelismo
    real para no depender de timing en el test."""

    class _Immediate:
        def __init__(self, target=None, daemon=None, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

        def join(self, *a, **kw):
            pass

    monkeypatch.setattr(_threading_mod, "Thread", _Immediate)


def _app(smoke=None, targets=None):
    return {
        "id": "miapp",
        "artifact": {"kind": "folder", "path": "C:\\build\\miapp\\out"},
        "targets": targets or {
            "__local__": {
                "install_path": "D:\\apps\\miapp",
                "smoke": smoke or {"kind": "none", "url": None, "command": None},
                "pre_switch": None,
                "post_switch": None,
                "protected": False,
            },
        },
    }


class FakeTransport:
    """Transporte fake compartido: `sequence` (lista) graba (target_key, kind, detalle)
    en orden de invocación real — usado para verificar despacho/orden (C2/C5 v2)."""

    def __init__(self, target_key: str, sequence: list, script: dict | None = None):
        self.target_key = target_key
        self.sequence = sequence
        self.script = script or {}

    def _resolve(self, key: str) -> dict:
        for pattern, result in self.script.items():
            if pattern in key:
                return dict(result() if callable(result) else result)
        return {"ok": True, "error": None, "stdout": "", "stderr": "", "exit_code": 0}

    def run(self, command, *, timeout_s, read_only, run_id=None):
        self.sequence.append((self.target_key, "run", command, read_only))
        return self._resolve(command or "")

    def push_file(self, local_path, remote_path, *, timeout_s, run_id=None):
        self.sequence.append((self.target_key, "push_file", remote_path, False))
        return self._resolve("push_file")


def _plan_for(app, target_key="__local__", version_id="20260710-153000-ab12cd34", retain=3):
    from services import deploy_planner as planner
    target_cfg = app["targets"][target_key]
    plan = planner.build_deploy_plan(app, target_key, target_cfg, version_id, retain, 30)
    return plan


# ── build_artifact_zip ───────────────────────────────────────────────────────

def test_zip_desde_folder_y_desde_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "data_dir", lambda: tmp_path / "data")

    folder_src = tmp_path / "out"
    folder_src.mkdir()
    (folder_src / "a.txt").write_text("hola", encoding="utf-8")
    app_folder = _app()
    app_folder["artifact"] = {"kind": "folder", "path": str(folder_src)}
    result = ex.build_artifact_zip(app_folder)
    assert Path(result["zip_path"]).exists()
    assert result["size_mb"] >= 0
    assert len(result["sha256"]) == 64

    zip_src = tmp_path / "prebuilt.zip"
    zip_src.write_bytes(b"PK\x03\x04fake-zip-bytes")
    app_zip = _app(); app_zip["id"] = "otraapp"
    app_zip["artifact"] = {"kind": "zip", "path": str(zip_src)}
    result2 = ex.build_artifact_zip(app_zip)
    assert Path(result2["zip_path"]).exists()
    assert result2["sha256"] != result["sha256"]


def test_zip_supera_tope_error_legible(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(ex, "MAX_ARTIFACT_MB", 0)  # cualquier archivo lo supera
    zip_src = tmp_path / "prebuilt.zip"
    zip_src.write_bytes(b"algo-de-contenido")
    app = _app()
    app["artifact"] = {"kind": "zip", "path": str(zip_src)}
    with pytest.raises(ValueError, match="supera el tope"):
        ex.build_artifact_zip(app)


# ── execute_plan ─────────────────────────────────────────────────────────────

def test_execute_plan_exito_completo_ledger_success(st, flags_on):
    app = _app()
    plan = _plan_for(app)
    sequence: list = []
    transport = FakeTransport("__local__", sequence)
    entry = ex.execute_plan(
        "dr-1", app, "__local__", plan, transport,
        version_id="20260710-153000-ab12cd34", zip_local="C:\\zip\\x.zip",
    )
    assert entry["status"] == "success"
    ledger_entry = store.read_ledger(app_id="miapp")[0]
    assert ledger_entry["status"] == "success"
    assert all(s["ok"] for s in ledger_entry["steps"])


def test_falla_en_transfer_corta_y_marca_failed(st, flags_on):
    app = _app()
    plan = _plan_for(app)
    sequence: list = []
    transport = FakeTransport("__local__", sequence, script={"push_file": {"ok": False, "error": "winrm_error"}})
    entry = ex.execute_plan(
        "dr-2", app, "__local__", plan, transport,
        version_id="v1", zip_local="C:\\zip\\x.zip",
    )
    assert entry["status"] == "failed"
    names_run = [s["name"] for s in entry["steps"]]
    assert names_run[-1] == "transfer"
    assert "unpack" not in names_run  # se cortó ahí, no siguió


def test_smoke_falla_marca_failed_smoke(st, flags_on):
    smoke = {"kind": "ps", "url": None, "command": "Test-Something"}
    app = _app(smoke=smoke)
    plan = _plan_for(app)
    sequence: list = []
    transport = FakeTransport(
        "__local__", sequence,
        script={"Test-Something": {"ok": False, "stdout": "", "stderr": "boom"}},
    )
    entry = ex.execute_plan(
        "dr-3", app, "__local__", plan, transport,
        version_id="v1", zip_local="C:\\zip\\x.zip",
    )
    assert entry["status"] == "failed_smoke"


def test_smoke_http_parsea_status(st, flags_on):
    smoke = {"kind": "http", "url": "http://localhost:8080/health", "command": None}
    app = _app(smoke=smoke)
    plan = _plan_for(app)
    sequence: list = []
    transport = FakeTransport(
        "__local__", sequence,
        script={"Invoke-WebRequest": {"ok": True, "stdout": "200", "stderr": ""}},
    )
    entry = ex.execute_plan(
        "dr-4", app, "__local__", plan, transport,
        version_id="v1", zip_local="C:\\zip\\x.zip",
    )
    assert entry["status"] == "success"
    assert entry["smoke"]["ok"] is True

    # Ahora un 500 -> failed_smoke
    sequence2: list = []
    transport2 = FakeTransport(
        "__local__", sequence2,
        script={"Invoke-WebRequest": {"ok": True, "stdout": "500", "stderr": ""}},
    )
    entry2 = ex.execute_plan(
        "dr-5", app, "__local__", plan, transport2,
        version_id="v1", zip_local="C:\\zip\\x.zip",
    )
    assert entry2["status"] == "failed_smoke"


def test_rollback_no_llama_push_file(st, flags_on):
    from services import deploy_planner as planner
    app = _app()
    target_cfg = app["targets"]["__local__"]
    plan = planner.build_rollback_plan(app, "__local__", target_cfg, "v-old", 30)
    sequence: list = []
    transport = FakeTransport("__local__", sequence)
    entry = ex.execute_plan(
        "dr-6", app, "__local__", plan, transport, version_id="v-old", action="rollback",
    )
    assert entry["status"] == "success"
    assert entry["action"] == "rollback"
    assert not any(call[1] == "push_file" for call in sequence)


# ── prune (C2 v2) ────────────────────────────────────────────────────────────

def test_prune_lista_solo_viejas(st, flags_on):
    app = _app()
    plan = _plan_for(app, retain=2)
    sequence: list = []
    transport = FakeTransport(
        "__local__", sequence,
        script={
            "Get-ChildItem": {"ok": True, "stdout": "v1\nv2\nv3\nv4", "stderr": ""},
        },
    )
    entry = ex.execute_plan(
        "dr-7", app, "__local__", plan, transport,
        version_id="v4", zip_local="C:\\zip\\x.zip", retain=2,
    )
    assert entry["status"] == "success"
    rmdir_calls = [c for c in sequence if c[1] == "run" and "rmdir /S /Q" in c[2]]
    deleted = {c[2].split("releases\\")[1].strip('"') for c in rmdir_calls}
    assert deleted == {"v1", "v2"}  # retiene v3,v4 (2 mas nuevas) + v4=current


def test_prune_despacho_lista_filtra_borra(st, flags_on):
    """C2 v2: la secuencia real es (1) listar read_only -> (2) filtrar puro
    -> (3) borrar por nombre, EN ese orden."""
    app = _app()
    plan = _plan_for(app, retain=1)
    sequence: list = []
    transport = FakeTransport(
        "__local__", sequence,
        script={"Get-ChildItem": {"ok": True, "stdout": "v1\nv2", "stderr": ""}},
    )
    ex.execute_plan(
        "dr-8", app, "__local__", plan, transport,
        version_id="v2", zip_local="C:\\zip\\x.zip", retain=1,
    )
    prune_related = [c for c in sequence if c[2].startswith("Get-ChildItem") or "rmdir /S /Q" in c[2]]
    assert prune_related[0][2].startswith("Get-ChildItem")
    assert prune_related[0][3] is True  # read_only=True para el listado
    assert all("rmdir" in c[2] for c in prune_related[1:])
    assert all(c[3] is False for c in prune_related[1:])  # borrar es write


def test_housekeeping_falla_no_degrada_success(st, flags_on):
    app = _app()
    plan = _plan_for(app, retain=2)
    sequence: list = []
    transport = FakeTransport(
        "__local__", sequence,
        script={"Get-ChildItem": {"ok": False, "error": "winrm_error", "stdout": "", "stderr": ""}},
    )
    entry = ex.execute_plan(
        "dr-9", app, "__local__", plan, transport,
        version_id="v1", zip_local="C:\\zip\\x.zip", retain=2,
    )
    assert entry["status"] == "success"  # housekeeping (prune) fallo NO degrada
    prune_step = next(s for s in entry["steps"] if s["name"] == "prune")
    assert prune_step["ok"] is False


def test_cleanup_borra_zip_incoming(st, flags_on):
    app = _app()
    plan = _plan_for(app)
    sequence: list = []
    transport = FakeTransport("__local__", sequence)
    entry = ex.execute_plan(
        "dr-10", app, "__local__", plan, transport,
        version_id="20260710-153000-ab12cd34", zip_local="C:\\zip\\x.zip",
    )
    cleanup_calls = [c for c in sequence if c[1] == "run" and "Remove-Item" in c[2]]
    assert len(cleanup_calls) == 1
    assert cleanup_calls[0][2] == (
        "Remove-Item -LiteralPath 'D:\\apps\\miapp\\incoming\\20260710-153000-ab12cd34.zip' -Force"
    )
    cleanup_step = next(s for s in entry["steps"] if s["name"] == "cleanup")
    assert cleanup_step["ok"] is True


# ── LocalTransport ───────────────────────────────────────────────────────────

def test_local_transport_push_valida_ruta_absoluta(tmp_path):
    t = ex.LocalTransport()
    local = tmp_path / "art.zip"
    local.write_bytes(b"x")

    r1 = t.push_file(str(local), "relative\\path.zip", timeout_s=10)
    assert r1["ok"] is False and r1["error"] == "invalid_remote_path"

    r2 = t.push_file(str(tmp_path / "no-existe.zip"), "D:\\x\\y.zip", timeout_s=10)
    assert r2["ok"] is False and r2["error"] == "local_file_not_found"

    dest = tmp_path / "dest_dir" / "y.zip"
    r3 = t.push_file(str(local), str(dest), timeout_s=10)
    assert r3["ok"] is True
    assert dest.exists()


# ── locks / orquestación async (C5 v2) ──────────────────────────────────────

def test_lock_impide_segundo_deploy_mismo_destino(st, flags_on):
    app = _app()
    store.acquire_run_lock("miapp", "__local__")  # pre-ocupa el lock
    plan = _plan_for(app)
    results = ex.start_deploy_async(
        app, ["__local__"],
        {"__local__": {"plan": plan, "version_id": "v1", "zip_local": "C:\\zip\\x.zip"}},
    )
    assert results == [{"target": "__local__", "error": "deploy_in_progress"}]


def test_lock_parcial_ejecuta_libres_y_reporta_ocupados(st, flags_on, synchronous_thread, monkeypatch):
    app = _app(targets={
        "__local__": {"install_path": "D:\\apps\\miapp", "smoke": {"kind": "none"}, "protected": False},
        "srv1": {"install_path": "D:\\apps\\miapp", "smoke": {"kind": "none"}, "protected": False},
    })
    store.acquire_run_lock("miapp", "srv1")  # ocupa SOLO srv1

    sequence: list = []
    monkeypatch.setattr(ex, "make_transport", lambda tk: FakeTransport(tk, sequence))

    plans = {
        "__local__": {"plan": _plan_for(app, "__local__"), "version_id": "v1", "zip_local": "C:\\zip\\x.zip"},
        "srv1": {"plan": _plan_for(app, "srv1"), "version_id": "v1", "zip_local": "C:\\zip\\x.zip"},
    }
    results = ex.start_deploy_async(app, ["__local__", "srv1"], plans)
    by_target = {r["target"]: r for r in results}
    assert by_target["srv1"] == {"target": "srv1", "error": "deploy_in_progress"}
    assert "run_id" in by_target["__local__"]
    assert any(c[0] == "__local__" for c in sequence)
    assert not any(c[0] == "srv1" for c in sequence)  # nunca se ejecutó


def test_orden_multi_destino_un_solo_thread_y_en_orden(st, flags_on, synchronous_thread, monkeypatch):
    app = _app(targets={
        "b-server": {"install_path": "D:\\apps\\miapp", "smoke": {"kind": "none"}, "protected": False},
        "a-server": {"install_path": "D:\\apps\\miapp", "smoke": {"kind": "none"}, "protected": False},
    })
    sequence: list = []
    monkeypatch.setattr(ex, "make_transport", lambda tk: FakeTransport(tk, sequence))
    plans = {
        "b-server": {"plan": _plan_for(app, "b-server"), "version_id": "v1", "zip_local": "C:\\zip\\x.zip"},
        "a-server": {"plan": _plan_for(app, "a-server"), "version_id": "v1", "zip_local": "C:\\zip\\x.zip"},
    }
    # Orden elegido por el operador: b-server PRIMERO (canary), luego a-server.
    results = ex.start_deploy_async(app, ["b-server", "a-server"], plans)
    assert all("run_id" in r for r in results)

    targets_en_orden_de_aparicion = []
    for call in sequence:
        if call[0] not in targets_en_orden_de_aparicion:
            targets_en_orden_de_aparicion.append(call[0])
    assert targets_en_orden_de_aparicion == ["b-server", "a-server"]
