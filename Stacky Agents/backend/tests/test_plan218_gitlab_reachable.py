"""tests/test_plan218_gitlab_reachable.py -- Plan 218 F0: prueba de vida de GitLab.

Cubre los 4 defectos D1..D4 (§2.1 del plan) que hacían que el camino GitLab
fuese INALCANZABLE, y la auditoría de binding de flags (flag_binding_audit).

REGLA DURA (P4): estos tests NO parchean el módulo `config` ni el provider.
Cuando hace falta un doble, se dobla el TRANSPORTE (GitLabClient) y el doble
declara la MISMA firma que el real (verificado con inspect.signature).
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config  # noqa: E402  (el MÓDULO, a propósito: el test documenta la causa raíz)


# ── D1/D2: la flag vive en la INSTANCIA, no en el módulo ──────────────────────

def test_config_module_no_expone_flags_de_instancia():
    """Causa raíz de D1/D2: `config` (módulo) NO tiene las flags; `config.config` sí.

    Este test documenta el defecto, no lo parchea. Si algún día alguien mueve las
    flags al módulo, este test avisa (y el fix de F0 pasaría a ser innecesario).
    """
    assert not hasattr(config, "STACKY_GITLAB_ENABLED")
    assert hasattr(config.config, "STACKY_GITLAB_ENABLED")


def _stub_ctx(tracker_type: str = "gitlab"):
    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.tracker_type = tracker_type
    ctx.organization = "myorg"
    ctx.tracker_project = "grupo/proyecto"
    ctx.stacky_project_name = "DEMO"
    ctx.auth_path = None
    ctx.workspace_root = None
    return ctx


def test_factory_devuelve_gitlab_con_flag_on(monkeypatch):
    """D1: con la flag ON en la INSTANCIA, la fábrica devuelve el provider GitLab."""
    import services.tracker_provider as tp

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")
    monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", True)
    monkeypatch.setattr(tp, "resolve_project_context", lambda **kw: _stub_ctx("gitlab"))

    provider = tp.get_tracker_provider("DEMO")

    assert provider.name == "gitlab"


def test_factory_rechaza_gitlab_con_flag_off(monkeypatch):
    """El kill-switch sigue intacto: flag OFF ⇒ TrackerConfigError."""
    import services.tracker_provider as tp
    from services.tracker_provider import TrackerConfigError

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")
    monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", False)
    monkeypatch.setattr(tp, "resolve_project_context", lambda **kw: _stub_ctx("gitlab"))

    with pytest.raises(TrackerConfigError, match="STACKY_GITLAB_ENABLED=false"):
        tp.get_tracker_provider("DEMO")


def test_gitlab_provider_lee_group_y_epics_de_instancia(monkeypatch):
    """D2: _group y _epics_native salen de config.config, no del módulo."""
    from services.gitlab_provider import GitLabTrackerProvider

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")
    monkeypatch.setattr(config.config, "STACKY_GITLAB_GROUP", "g1")
    monkeypatch.setattr(config.config, "STACKY_GITLAB_EPICS_NATIVE", True)

    provider = GitLabTrackerProvider(project="grupo/proyecto")

    assert provider._group == "g1"
    assert provider._epics_native is True


# ── D3: kwarg inexistente en el constructor ───────────────────────────────────

def test_gitlab_ci_provider_construye(monkeypatch):
    """D3: GitLabCIProvider se construía con project_name= (kwarg inexistente)."""
    from services.gitlab_ci_provider import GitLabCIProvider

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")

    provider = GitLabCIProvider(project="grupo/proyecto")

    assert provider._delegate.name == "gitlab"


def test_gitlab_variables_provider_construye(monkeypatch):
    """D3: idéntico defecto en GitLabVariablesProvider."""
    from services.gitlab_variables import GitLabVariablesProvider

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")

    provider = GitLabVariablesProvider(project="grupo/proyecto")

    assert provider._project == "grupo/proyecto"


# ── D4: firmas reales de GitLabClient ─────────────────────────────────────────

class _SignatureCheckedClient:
    """Doble de GitLabClient que declara EXACTAMENTE la firma real de los métodos
    que usa GitLabVariablesProvider. Una llamada con la firma equivocada levanta
    TypeError, igual que el cliente real."""

    def __init__(self):
        self.calls: list[dict] = []

    def _project_path(self) -> str:
        return "grupo%2Fproyecto"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        files: dict | None = None,
        _retry: int = 0,
    ) -> tuple[object, dict]:
        self.calls.append(
            {"method": method, "path": path, "params": params, "json_body": json_body}
        )
        return {}, {}

    def _request_paginated(
        self,
        path: str,
        *,
        params: dict | None = None,
        page_cap: int = 20,
    ) -> list:
        self.calls.append({"method": "GET", "path": path, "params": params})
        return [{"key": "K1", "masked": True, "protected": False}]


def _assert_doble_es_fiel() -> None:
    """Guard del guard: si GitLabClient cambia de firma, el doble deja de valer."""
    from services.gitlab_client import GitLabClient

    for method in ("_request", "_request_paginated"):
        real = inspect.signature(getattr(GitLabClient, method))
        fake = inspect.signature(getattr(_SignatureCheckedClient, method))
        assert list(real.parameters) == list(fake.parameters), (
            f"{method}: nombres de parámetros distintos entre real y doble"
        )
        assert [p.kind for p in real.parameters.values()] == [
            p.kind for p in fake.parameters.values()
        ], f"{method}: el doble no refleja la firma real"


def _variables_provider_con_doble(monkeypatch) -> tuple[object, _SignatureCheckedClient]:
    from services.gitlab_variables import GitLabVariablesProvider

    _assert_doble_es_fiel()
    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")
    provider = GitLabVariablesProvider(project="grupo/proyecto")
    doble = _SignatureCheckedClient()
    provider._client = doble
    return provider, doble


def test_gitlab_variables_list_usa_firma_real(monkeypatch):
    """D4: _request_paginated NO acepta `method` posicional (es GET por definición).

    `has_value` es None (no True): el plan 260 F1 cerró el hardcodeo a True —
    GitLab enmascara el valor de una variable secreta en el listado, así que
    sin una lectura aparte no hay forma honesta de saber si tiene valor.
    """
    provider, doble = _variables_provider_con_doble(monkeypatch)

    result = provider.list_variables()

    assert result == [{"key": "K1", "is_secret": True, "has_value": None, "masked": True}]
    assert doble.calls[0]["path"].endswith("/variables")
    assert not doble.calls[0]["path"].startswith("GET")


def test_gitlab_variables_set_usa_json_body(monkeypatch):
    """D4: el cliente real recibe json_body=, no json=."""
    from services.tracker_provider import TrackerApiError

    provider, doble = _variables_provider_con_doble(monkeypatch)

    def _request(method, path, *, params=None, json_body=None, files=None, _retry=0):
        doble.calls.append({"method": method, "path": path, "json_body": json_body})
        if method == "GET":
            raise TrackerApiError(404, "no existe", kind="not_found")
        return {}, {}

    provider._client._request = _request

    result = provider.set_variable("K1", "v1", secret=False)

    assert result["key"] == "K1"
    escrituras = [c for c in doble.calls if c["method"] in ("POST", "PUT")]
    assert escrituras, "no se registró ninguna escritura"
    assert escrituras[-1]["json_body"] == {
        "key": "K1", "value": "v1", "masked": False, "protected": False,
    }


# ── [ADICIÓN ARQUITECTO 1] flag_binding_audit ────────────────────────────────

def _write_module(tmp_path: Path, name: str, source: str) -> Path:
    pkg = tmp_path / "services"
    pkg.mkdir(parents=True, exist_ok=True)
    target = pkg / name
    target.write_text(source, encoding="utf-8")
    return target


def test_audit_no_marca_binding_de_instancia(tmp_path):
    """EL test que impide que el centinela vuelva a ser destructivo.

    `from config import config` bindea la INSTANCIA: leer config.FLAG es CORRECTO
    y NO se reporta. Hay ~65 sitios así en el repo (§2.1 del plan).
    """
    from services.flag_binding_audit import scan

    _write_module(
        tmp_path,
        "ok_instancia.py",
        "from config import config\n\n"
        "def f():\n"
        "    return getattr(config, 'STACKY_X', False) or config.STACKY_Y\n",
    )

    result = scan(root=tmp_path, scan_dirs=("services",))

    assert result["violations"] == []
    assert result["violation_count"] == 0


def test_audit_marca_binding_de_modulo(tmp_path):
    """`import config` + getattr(config, 'FLAG') ⇒ rama muerta ⇒ violación."""
    from services.flag_binding_audit import scan

    _write_module(
        tmp_path,
        "malo_getattr.py",
        "import config\n\n"
        "def f():\n"
        "    return getattr(config, 'STACKY_GITLAB_ENABLED', False)\n",
    )

    result = scan(root=tmp_path, scan_dirs=("services",))

    assert result["violation_count"] == 1
    v = result["violations"][0]
    assert v["file"] == "services/malo_getattr.py"
    assert v["line"] == 4
    assert v["attr"] == "STACKY_GITLAB_ENABLED"
    assert v["name"] == "config"
    assert v["binding"] == "module"
    assert "services/malo_getattr.py" in result["module_bound_files"]


def test_audit_marca_acceso_directo(tmp_path):
    """Cobertura que el regex del v1 NO tenía: `if config.STACKY_X:`."""
    from services.flag_binding_audit import scan

    _write_module(
        tmp_path,
        "malo_directo.py",
        "import config\n\n"
        "def f():\n"
        "    if config.STACKY_X:\n"
        "        return 1\n"
        "    return 0\n",
    )

    result = scan(root=tmp_path, scan_dirs=("services",))

    assert result["violation_count"] == 1
    assert result["violations"][0]["attr"] == "STACKY_X"


def test_audit_no_marca_config_config(tmp_path):
    """`import config` + config.config.FLAG es CORRECTO (patrón de ci_provider.py:121)."""
    from services.flag_binding_audit import scan

    _write_module(
        tmp_path,
        "ok_config_config.py",
        "import config\n"
        "import config as _config\n\n"
        "def f():\n"
        "    a = getattr(config.config, 'STACKY_X', False)\n"
        "    b = _config.config.STACKY_Y\n"
        "    return a or b\n",
    )

    result = scan(root=tmp_path, scan_dirs=("services",))

    assert result["violations"] == []


def test_audit_del_repo_real_esta_en_cero_para_los_5_sitios_conocidos():
    """Tras F0, el seam (tracker_provider + gitlab_provider) queda en CERO.

    El resto del repo se congela en flag_binding_baseline.json — RATCHET, no
    exigencia de cero global: arreglar una flag muerta ajena cambia comportamiento
    y necesita su propio subplan (P11 — no degradar).
    """
    from services.flag_binding_audit import scan, render_report

    result = scan()
    seam = [
        v for v in result["violations"]
        if "tracker_provider" in v["file"] or "gitlab_provider" in v["file"]
    ]
    assert seam == [], f"violaciones en el seam:\n{render_report({'violations': seam})}"

    baseline_path = _BACKEND / "tests" / "flag_binding_baseline.json"
    assert baseline_path.exists(), "falta el baseline generado (ver comando en F0)"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert result["violation_count"] <= baseline["violation_count"], (
        "el acoplamiento de flags al MÓDULO config creció:\n"
        + render_report(result)
    )
