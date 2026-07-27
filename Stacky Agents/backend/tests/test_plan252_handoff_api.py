"""Plan 252 F4 — preview, build y descarga con las tres guardas. 12 tests."""
from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

BASE = "/api/pipeline-handoff"

# literal PARTIDO: un token entero en el fuente dispara la push-protection de GitHub
_GLPAT = "glpat-" + "y" * 20


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    import config as cfg
    import runtime_paths

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield tmp_path


def _body(**kw):
    base = {"pipeline_name": "AgendaWeb CI", "provider": "ado",
            "yaml_files": {"pipelines/ci.yml": "stages: []\n"},
            "script_files": {"scripts/Deploy-Local.ps1": "Write-Host hola\n"},
            "pipeline_deploys": True, "spec": {}}
    base.update(kw)
    return base


def _bundles(tmp_path):
    d = tmp_path / "pipeline_handoff" / "bundles"
    return sorted(p.name for p in d.glob("*.zip")) if d.is_dir() else []


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_flag_off_404_en_los_3_endpoints(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED", False,
                        raising=False)
    c = app.test_client()
    assert c.get(BASE + "/frontier").status_code == 404
    assert c.post(BASE + "/build", json=_body()).status_code == 404
    assert c.get(BASE + "/0123456789abcdef/download").status_code == 404


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_frontier_devuelve_14_acciones(app):
    r = app.test_client().get(BASE + "/frontier?deploys=true")
    assert r.status_code == 200
    body = r.get_json()
    assert body["catalog_version"] == "252.1"
    assert len(body["actions"]) == 14
    for a in body["actions"]:
        assert a["reason"].strip(), a["id"]
        assert a["effective"] in ("CAN", "CANNOT", "CANNOT_NOW", "UNKNOWN")


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_frontier_sin_deploys_devuelve_12(app):
    r = app.test_client().get(BASE + "/frontier?deploys=false")
    assert r.status_code == 200
    assert len(r.get_json()["actions"]) == 12


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_build_devuelve_bundle_id_y_persiste(app, _entorno):
    r = app.test_client().post(BASE + "/build", json=_body())
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert len(body["bundle_id"]) == 16
    assert body["bytes"] > 0
    assert body["manifest"]["pipeline_name"] == "AgendaWeb CI"
    assert _bundles(_entorno) == ["%s.zip" % body["bundle_id"]]


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_build_es_idempotente(app, _entorno):
    """KPI-1 end to end: mismo body -> mismo id Y mismo sha256 del archivo."""
    c = app.test_client()
    a = c.post(BASE + "/build", json=_body()).get_json()
    ruta = _entorno / "pipeline_handoff" / "bundles" / ("%s.zip" % a["bundle_id"])
    sha_a = hashlib.sha256(ruta.read_bytes()).hexdigest()
    b = c.post(BASE + "/build", json=_body()).get_json()
    assert a["bundle_id"] == b["bundle_id"]
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == sha_a


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_build_con_secreto_devuelve_409(app, _entorno):
    """KPI-2 — falla CERRADO: 409 y CERO archivos en el directorio de paquetes."""
    r = app.test_client().post(BASE + "/build", json=_body(
        script_files={"scripts/x.ps1": "$t = '%s'\n" % _GLPAT}))
    assert r.status_code == 409
    assert "NO se generó" in r.get_json()["error"]
    assert _bundles(_entorno) == []


def test_build_body_invalido_400(app):
    c = app.test_client()
    assert c.post(BASE + "/build", json=_body(pipeline_name="")).status_code == 400
    assert c.post(BASE + "/build", json=_body(provider="jenkins")).status_code == 400
    assert c.post(BASE + "/build", json=_body(yaml_files={})).status_code == 400


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_download_ok(app):
    c = app.test_client()
    bid = c.post(BASE + "/build", json=_body()).get_json()["bundle_id"]
    r = c.get("%s/%s/download" % (BASE, bid))
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/zip")
    nombres = zipfile.ZipFile(io.BytesIO(r.data)).namelist()
    assert "README.md" in nombres and "MANIFEST.json" in nombres


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_download_desconocido_404(app):
    r = app.test_client().get(BASE + "/0123456789abcdef/download")
    assert r.status_code == 404


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_download_traversal_404(app):
    c = app.test_client()
    for malo in ("..%2f..%2fetc%2fpasswd", "ABCDEF0123456789", "xxxx"):
        r = c.get("%s/%s/download" % (BASE, malo))
        assert r.status_code in (404, 400), (malo, r.status_code)
        assert r.status_code != 500


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_download_fuera_de_raiz_400(app, tmp_path, monkeypatch):
    from services import pipeline_handoff_bundle as hb

    fuera = tmp_path / "fuera.zip"
    fuera.write_bytes(b"PK")
    monkeypatch.setattr(hb, "bundle_path", lambda _bid: fuera)
    r = app.test_client().get(BASE + "/0123456789abcdef/download")
    assert r.status_code == 400


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_ningun_hook_dispara_build():
    """HITL por construccion: los unicos call-sites de build_bundle son el endpoint y
    los tests. Ningun scheduler, watcher ni hook lo llama."""
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    call_sites = []
    for ruta in list(backend.glob("**/*.py")):
        partes = ruta.parts
        if "__pycache__" in partes or ".venv" in partes or "venv" in partes:
            continue
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "build_bundle(" in texto and ruta.name != "pipeline_handoff_bundle.py":
            call_sites.append(ruta.relative_to(backend).as_posix())
    permitidos = {"api/pipeline_handoff.py"}
    ajenos = [c for c in call_sites
              if c not in permitidos and not c.startswith("tests/")]
    assert ajenos == [], ajenos


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_health_publica_la_llave(app):
    r = app.test_client().get("/api/devops/health")
    assert r.status_code == 200
    assert "handoff_bundle_enabled" in r.get_json()


def test_guard_de_descarga_usa_commonpath():
    from pathlib import Path

    fuente = (Path(__file__).resolve().parent.parent / "api"
              / "pipeline_handoff.py").read_text(encoding="utf-8")
    assert "commonpath" in fuente
