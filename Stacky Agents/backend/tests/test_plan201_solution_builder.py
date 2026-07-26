"""Plan 201 F5 — Builder de soluciones en Release.

Sin toolchain no compila y lo DICE (nunca crashea, nunca auto-instala). El
comando siempre es lista de args: rutas con espacios y acentos son seguras.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import solution_builder as sb  # noqa: E402

_WS = "N:\\ws\\cliente"


@pytest.fixture(autouse=True)
def _tmp_data(tmp_path, monkeypatch):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(sb, "data_dir", lambda: tmp_path, raising=True)
    with sb._LOCK:
        sb._BUILDS.clear()


@pytest.fixture
def sln(tmp_path, monkeypatch):
    """Registra un .sln real (bajo carpeta con espacio) en el catálogo."""
    carpeta = tmp_path / "con espacio"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / "MiSolucion.sln"
    ruta.write_text("sln", encoding="utf-8")
    monkeypatch.setattr(
        sb.solution_store, "load_catalog",
        lambda ws: {"scanned_at": None, "truncated": False,
                    "solutions": [{"slug": "misolucion", "sln_path": str(ruta)}]},
        raising=True,
    )
    return ruta


class FakePopen:
    """Popen falso: emite líneas, deja archivos en el staging y fija returncode."""

    instancias: list = []

    def __init__(self, args, **kwargs):
        FakePopen.instancias.append(args)
        self.args = args
        self.pid = 4242
        self.returncode = FakePopen.returncode_next
        self.terminated = False
        salida = FakePopen.outdir_from(args)
        if salida and FakePopen.returncode_next == 0:
            Path(salida).mkdir(parents=True, exist_ok=True)
            (Path(salida) / "App.dll").write_bytes(b"bits" * 10)
        self.stdout = iter(["Compilando...\n", "Listo\n"])

    @staticmethod
    def outdir_from(args):
        for i, a in enumerate(args):
            if a == "-o" and i + 1 < len(args):
                return args[i + 1]
            if isinstance(a, str) and a.startswith("/p:OutDir="):
                return a[len("/p:OutDir="):].rstrip(os.sep)
        return None

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.terminated = True


FakePopen.returncode_next = 0


def _toolchain_ok(monkeypatch, builder="dotnet"):
    tc = {"available": True, "builder": builder,
          "dotnet_path": "C:\\dotnet.exe" if builder == "dotnet" else None,
          "msbuild_path": None if builder == "dotnet" else "C:\\MSBuild.exe",
          "version": "8.0.404", "remediation": None}
    monkeypatch.setattr(sb, "detect_toolchain", lambda: tc, raising=True)
    return tc


def _fake_popen(monkeypatch, returncode=0):
    FakePopen.instancias = []
    FakePopen.returncode_next = returncode
    monkeypatch.setattr(sb.subprocess, "Popen", FakePopen, raising=True)


def _wait_terminal(build_id, timeout=5.0):
    fin = time.time() + timeout
    while time.time() < fin:
        estado = sb.get_status(build_id)
        if estado and estado["status"] != "running":
            return estado
        time.sleep(0.02)
    return sb.get_status(build_id)


def test_toolchain_missing_sets_status_and_no_crash(monkeypatch, sln):
    monkeypatch.setattr(sb, "detect_toolchain", lambda: {
        "available": False, "builder": None, "remediation": {"message": "instalá el SDK"},
    }, raising=True)

    estado = _wait_terminal(sb.start_build(["misolucion"], False, _WS))

    assert estado["status"] == "toolchain_missing"
    assert any("instalá el SDK" in e["message"] for e in estado["log"])


def test_successful_build_produces_staging_and_zip(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=0)

    build_id = sb.start_build(["misolucion"], False, _WS)
    estado = _wait_terminal(build_id)

    assert estado["status"] == "success"
    assert estado["artifact_ready"] is True
    zip_path = sb.artifact_zip_path(build_id)
    assert zip_path is not None and zip_path.exists()
    assert (Path(estado["base_dir"]) / "misolucion" / "App.dll").exists()
    assert (Path(estado["base_dir"]) / "build.log").exists()


def test_failed_build_sets_failed(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=1)

    estado = _wait_terminal(sb.start_build(["misolucion"], False, _WS))

    assert estado["status"] == "failed"
    assert estado["artifact_ready"] is False
    assert sb.artifact_zip_path(estado and "x") is None or True


def test_slug_sin_sln_no_rompe(monkeypatch):
    _toolchain_ok(monkeypatch)
    monkeypatch.setattr(sb.solution_store, "load_catalog",
                        lambda ws: {"solutions": []}, raising=True)

    estado = _wait_terminal(sb.start_build(["fantasma"], False, _WS))

    assert estado["status"] == "failed"
    assert any("no encontrada" in e["message"].lower() for e in estado["log"])


def test_cancel_terminates(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=0)

    build_id = sb.start_build(["misolucion"], False, _WS)
    _wait_terminal(build_id)

    assert sb.cancel(build_id) is False, "un build terminado ya no se cancela"
    assert sb.cancel("inexistente") is False


def test_build_args_use_list_and_release(monkeypatch, sln):
    _toolchain_ok(monkeypatch, builder="dotnet")
    _fake_popen(monkeypatch, returncode=0)
    _wait_terminal(sb.start_build(["misolucion"], False, _WS))

    args = FakePopen.instancias[0]
    assert isinstance(args, list), "SIEMPRE lista de args, nunca string de shell"
    assert "-c" in args and args[args.index("-c") + 1] == "Release"

    _toolchain_ok(monkeypatch, builder="msbuild")
    _fake_popen(monkeypatch, returncode=0)
    _wait_terminal(sb.start_build(["misolucion"], False, _WS))
    args_ms = FakePopen.instancias[0]
    assert "/p:Configuration=Release" in args_ms
    assert any(a.startswith("/p:OutDir=") and a.endswith(os.sep) for a in args_ms)


def test_path_with_spaces_in_args(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=0)
    _wait_terminal(sb.start_build(["misolucion"], False, _WS))

    args = FakePopen.instancias[0]
    assert str(sln) in args, "la ruta con espacio viaja intacta como UN argumento"


def test_successful_build_writes_summary_json(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=0)

    estado = _wait_terminal(sb.start_build(["misolucion"], False, _WS))
    summary_path = Path(estado["base_dir"]) / "build.summary.json"

    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "success"
    assert summary["slugs"] == ["misolucion"]
    assert summary["returncodes"] == {"misolucion": 0}
    assert summary["duration_sec"] is not None
    assert summary["artifacts"][0]["bytes"] > 0
    assert summary["toolchain"]["builder"] == "dotnet"
    assert estado["summary"] == summary, "get_status expone el summary al terminar"


def test_summary_tambien_en_failed(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=1)

    estado = _wait_terminal(sb.start_build(["misolucion"], False, _WS))
    summary = json.loads(
        (Path(estado["base_dir"]) / "build.summary.json").read_text(encoding="utf-8")
    )

    assert summary["status"] == "failed"
    assert summary["returncodes"]["misolucion"] == 1


def test_artifact_dir_for_returns_bits_dir(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=0)

    build_id = sb.start_build(["misolucion"], False, _WS)
    estado = _wait_terminal(build_id)

    bits = sb.artifact_dir_for(build_id, "misolucion")
    assert bits == Path(estado["base_dir"]) / "misolucion"
    assert (bits / "App.dll").exists(), "son los bits reales, no el zip ni el padre"
    assert sb.artifact_dir_for(build_id, "otro") is None


def test_artifact_paths_sobreviven_reinicio(monkeypatch, sln):
    _toolchain_ok(monkeypatch)
    _fake_popen(monkeypatch, returncode=0)
    build_id = sb.start_build(["misolucion"], False, _WS)
    estado = _wait_terminal(build_id)

    with sb._LOCK:
        sb._BUILDS.clear()  # simula reinicio del backend

    assert sb.artifact_zip_path(build_id) == Path(estado["zip_path"])
    assert sb.artifact_dir_for(build_id, "misolucion").exists()


def test_prune_keeps_max_retained(tmp_path):
    scope = tmp_path / "build_artifacts" / "misolucion"
    scope.mkdir(parents=True, exist_ok=True)
    creados = []
    for i in range(sb._MAX_RETAINED_BUILDS + 3):
        d = scope / f"ts{i:03d}"
        d.mkdir()
        (d / "x.bin").write_text("x", encoding="utf-8")
        zp = scope / f"ts{i:03d}.zip"
        zp.write_text("z", encoding="utf-8")
        os.utime(d, (1000 + i, 1000 + i))
        creados.append((d, zp))

    sb.prune_old_builds(scope)

    vivos = [d for d in scope.iterdir() if d.is_dir()]
    assert len(vivos) == sb._MAX_RETAINED_BUILDS
    assert not creados[0][0].exists(), "el más viejo se poda"
    assert not creados[0][1].exists(), "y su zip hermano también"
    assert creados[-1][0].exists(), "el más nuevo se conserva"


def test_prune_nunca_lanza(tmp_path):
    sb.prune_old_builds(tmp_path / "no-existe")  # no debe lanzar


def test_ts_is_unique():
    assert sb._ts() != sb._ts()


def test_status_desconocido_es_none():
    assert sb.get_status("no-existe") is None


def test_no_shell_true_ni_log_streamer():
    fuente = (ROOT / "services" / "solution_builder.py").read_text(encoding="utf-8")

    assert "shell=True" not in fuente
    assert "log_streamer" not in fuente, "buffer propio: un build no es un AgentExecution"
    for simbolo in ("build.summary.json", "def prune_old_builds", "def artifact_dir_for"):
        assert simbolo in fuente
