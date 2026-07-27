"""Plan 215 F4 — runner de publish: estados, watchdog, cancel, ledger y poda."""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from services import solution_publisher as sp

_TC_OK = {"available": True, "builder": "dotnet", "dotnet_path": "dotnet",
          "msbuild_path": "msbuild", "version": "8.0"}
_TC_NONE = {"available": False, "builder": None, "dotnet_path": None,
            "msbuild_path": None, "version": None,
            "remediation": {"message": "Instalá el SDK de .NET"}}


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "artifacts_root", lambda: tmp_path / "solution_publish_artifacts")
    monkeypatch.setattr(sp, "_ledger_path", lambda: tmp_path / "solution_publish_runs.jsonl")
    with sp._LOCK:
        sp._RUNS.clear()
    yield
    with sp._LOCK:
        sp._RUNS.clear()


class _FakeProc:
    """Popen falso. `lines` se emiten y luego EOF; si `block` es True el stdout
    se queda esperando hasta que terminate() lo destrabe (proceso MUDO)."""

    def __init__(self, lines=(), returncode=0, block=False):
        self._lines = list(lines)
        self.returncode = returncode
        self.pid = 4242
        self._block = block
        self._released = threading.Event()
        self.terminated = False
        self.stdout = self._iter()

    def _iter(self):
        for ln in self._lines:
            yield ln
        if self._block:
            self._released.wait(timeout=20)

    def terminate(self):
        self.terminated = True
        self._released.set()

    def wait(self, timeout=None):
        return self.returncode


def _wait_done(run_id, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with sp._LOCK:
            st = (sp._RUNS.get(run_id) or {}).get("status")
        if st and st != "running":
            return st
        time.sleep(0.02)
    return "TIMEOUT_DEL_TEST"


def _stub_deps(monkeypatch, tmp_path, toolchain=_TC_OK, plan=None, cfg=None):
    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    sln = os.path.join(ws, "Mi.sln")
    open(sln, "w", encoding="utf-8").write("x")
    monkeypatch.setattr("services.build_toolchain.detect_toolchain", lambda: toolchain)
    monkeypatch.setattr(
        "services.solution_store.load_catalog",
        lambda w: {"solutions": [{"slug": "mi-sln", "sln_path": sln,
                                  "friendly_name": "Mi Sln", "projects": []}]},
    )
    monkeypatch.setattr(
        "services.publish_config_store.load_config",
        lambda w, s: cfg or {"mode": "auto", "configuration": "Release", "extra_args": []},
    )
    monkeypatch.setattr(
        "services.publish_profile_scanner.resolve_publish_plan",
        lambda sol, c, tc: plan or {"mode_effective": "build_only", "supported": True,
                                    "reason": "", "target": sln, "argv_tail": []},
    )
    return ws, sln


def test_toolchain_missing_sets_status(tmp_path, monkeypatch):
    ws, _ = _stub_deps(monkeypatch, tmp_path, toolchain=_TC_NONE)
    rid = sp.start_publish("mi-sln", ws)
    assert _wait_done(rid) == "toolchain_missing"


def test_unsupported_plan_sets_status_and_reason(tmp_path, monkeypatch):
    ws, sln = _stub_deps(monkeypatch, tmp_path, plan={
        "mode_effective": "msbuild_pubxml", "supported": False,
        "reason": "sin_pubxml_filesystem", "target": sln if False else "", "argv_tail": []})
    rid = sp.start_publish("mi-sln", ws)
    assert _wait_done(rid) == "unsupported"
    assert sp.get_status(rid)["error"] == "sin_pubxml_filesystem"


def test_solution_not_found_fails(tmp_path, monkeypatch):
    monkeypatch.setattr("services.build_toolchain.detect_toolchain", lambda: _TC_OK)
    monkeypatch.setattr("services.solution_store.load_catalog", lambda w: {"solutions": []})
    rid = sp.start_publish("fantasma", str(tmp_path))
    assert _wait_done(rid) == "failed"
    assert sp.get_status(rid)["error"] == "solucion_no_encontrada"


def test_success_produces_staging_summary_and_ledger_lines(tmp_path, monkeypatch):
    ws, _ = _stub_deps(monkeypatch, tmp_path)
    monkeypatch.setattr(sp.subprocess, "Popen",
                        lambda *a, **k: _FakeProc(lines=["compilando\n", "ok\n"]))
    rid = sp.start_publish("mi-sln", ws)
    assert _wait_done(rid) == "success"
    st = sp.get_status(rid)
    base = None
    with sp._LOCK:
        base = sp._RUNS[rid]["base_dir"]
    assert os.path.exists(os.path.join(base, "publish.summary.json"))
    assert os.path.exists(os.path.join(base, "publish.log"))
    summary = json.load(open(os.path.join(base, "publish.summary.json"), encoding="utf-8"))
    assert summary["status"] == "success"
    assert any("compilando" in e["message"] for e in st["log"])
    # ADICIÓN 1 — dos líneas de ledger por run.
    events = [json.loads(l) for l in open(sp._ledger_path(), encoding="utf-8") if l.strip()]
    assert [e["event"] for e in events if e["run_id"] == rid] == ["started", "finished"]


def test_failed_returncode_sets_failed_and_still_writes_summary(tmp_path, monkeypatch):
    ws, _ = _stub_deps(monkeypatch, tmp_path)
    monkeypatch.setattr(sp.subprocess, "Popen",
                        lambda *a, **k: _FakeProc(lines=["error NU1101: falta paquete\n"],
                                                  returncode=1))
    rid = sp.start_publish("mi-sln", ws)
    assert _wait_done(rid) == "failed"
    st = sp.get_status(rid)
    assert st["failure_class"]["code"] == "nuget_restore"


def test_cancel_terminates_immediately_without_new_output(tmp_path, monkeypatch):
    """C1 — el proceso está MUDO; cancel debe destrabarlo sin esperar output."""
    ws, _ = _stub_deps(monkeypatch, tmp_path)
    holder = {}

    def _mk(*a, **k):
        holder["proc"] = _FakeProc(lines=[], block=True)
        return holder["proc"]

    monkeypatch.setattr(sp.subprocess, "Popen", _mk)
    monkeypatch.setattr(sp, "_terminate_tree", lambda p: p.terminate())
    rid = sp.start_publish("mi-sln", ws)
    deadline = time.time() + 5
    while "proc" not in holder and time.time() < deadline:
        time.sleep(0.01)
    assert sp.cancel(rid) is True
    assert _wait_done(rid) == "cancelled"
    assert holder["proc"].terminated is True


def test_timeout_watchdog_kills_silent_process(tmp_path, monkeypatch):
    """C1 — un proceso mudo vence por watchdog, no por output."""
    ws, _ = _stub_deps(monkeypatch, tmp_path)
    monkeypatch.setattr(sp, "_PUBLISH_TIMEOUT_SEC", 1)
    holder = {}

    def _mk(*a, **k):
        holder["proc"] = _FakeProc(lines=[], block=True)
        return holder["proc"]

    monkeypatch.setattr(sp.subprocess, "Popen", _mk)
    monkeypatch.setattr(sp, "_terminate_tree", lambda p: p.terminate())
    rid = sp.start_publish("mi-sln", ws)
    assert _wait_done(rid, timeout=15) == "failed"
    assert sp.get_status(rid)["error"] == "timeout"
    assert holder["proc"].terminated is True


def test_argv_dotnet_publish_shape():
    plan = {"mode_effective": "dotnet_publish", "supported": True, "reason": "",
            "target": "A.csproj",
            "argv_tail": ["publish", "A.csproj", "-c", "Release", "--nologo"]}
    argv = sp._build_argv(plan, {"extra_args": ["/p:X=Y"]}, _TC_OK, "C:\\stage")
    assert argv[0] == "dotnet"
    assert argv[-1] == "/p:X=Y", "los extra_args van al FINAL"
    assert "-o" in argv and "C:\\stage" in argv


def test_argv_msbuild_pubxml_includes_deployonbuild_and_publishurl():
    plan = {"mode_effective": "msbuild_pubxml", "supported": True, "reason": "",
            "target": "A.csproj",
            "argv_tail": ["A.csproj", "/p:DeployOnBuild=true", "/p:PublishProfile=Prod"]}
    argv = sp._build_argv(plan, {}, _TC_OK, "C:\\stage")
    assert argv[0] == "msbuild"
    assert "/p:DeployOnBuild=true" in argv
    assert any(a.startswith("/p:publishUrl=") for a in argv)


def test_no_shell_true_and_no_log_streamer():
    src = open(sp.__file__, encoding="utf-8").read()
    assert "shell=True" not in src
    assert "log_streamer" not in src


def test_list_runs_newest_first_and_marks_interrupted(tmp_path):
    ledger = sp._ledger_path()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "started", "run_id": "r1", "slug": "s",
                             "workspace_root": "W", "started_at": "t0"}) + "\n")
        fh.write(json.dumps({"event": "finished", "run_id": "r1", "slug": "s",
                             "workspace_root": "W", "status": "success"}) + "\n")
        fh.write("{ linea corrupta\n")  # C11
        fh.write(json.dumps({"event": "started", "run_id": "r2", "slug": "s",
                             "workspace_root": "W", "started_at": "t1"}) + "\n")
    runs = sp.list_runs("W", "s")
    assert [r["run_id"] for r in runs] == ["r2", "r1"], "más nuevos primero"
    assert runs[0]["status"] == "interrupted", "started sin finished y sin memoria"
    assert runs[1]["status"] == "success"


def test_get_status_unknown_returns_none():
    assert sp.get_status("no-existe") is None


def test_classify_publish_failure_known_and_none():
    assert sp.classify_publish_failure(["error NU1101: x"])["code"] == "nuget_restore"
    assert sp.classify_publish_failure(["error MSB3644"])["code"] == "targeting_pack_missing"
    assert sp.classify_publish_failure(["error CS1002"])["code"] == "compile_error"
    assert sp.classify_publish_failure(["todo bien"]) is None
    assert sp.classify_publish_failure([]) is None


def test_prune_keeps_max_retained(tmp_path):
    scope = sp.artifacts_root() / "mi-sln"
    scope.mkdir(parents=True, exist_ok=True)
    for i in range(sp._MAX_RETAINED_RUNS + 3):
        d = scope / f"20260101_00000{i}_aaa{i}"
        d.mkdir()
        (d / "x.txt").write_text("x", encoding="utf-8")
        (scope / f"20260101_00000{i}_aaa{i}.zip").write_text("z", encoding="utf-8")
        time.sleep(0.01)
    sp.prune_old_publish_runs(scope)
    dirs = [p for p in scope.iterdir() if p.is_dir()]
    assert len(dirs) == sp._MAX_RETAINED_RUNS
    # C6 — los zips huérfanos de los podados también se van.
    zips = [p for p in scope.iterdir() if p.suffix == ".zip"]
    assert len(zips) == sp._MAX_RETAINED_RUNS


def test_build_assist_message_masks_and_includes_context():
    tok = "ghp_" + "A" * 36  # partido para no gatillar push-protection
    run = {"mode_effective": "build_only", "status": "failed", "returncode": 1,
           "argv": ["msbuild", "/p:Password=" + tok],
           "failure_class": {"code": "nuget_restore", "hint": "revisar feed"},
           "log": [{"message": "usando token " + tok}]}
    cfg = {"mode": "auto", "extra_args": ["/p:Token=" + tok]}
    msg = sp.build_assist_message(run, cfg, {"friendly_name": "Mi Sln", "sln_path": "C:\\a.sln"},
                                  {"available": True, "builder": "dotnet", "version": "8"})
    assert tok not in msg, "C3 — el masking cubre argv, config y tail"
    assert "nuget_restore" in msg
    assert "NO ejecutes nada" in msg
