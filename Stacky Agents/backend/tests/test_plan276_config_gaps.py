"""tests/test_plan276_config_gaps.py — Plan 276 F8.1.

P1-2: la rama LEGACY de `get_tracker_provider` construía
`GitLabTrackerProvider(project=project)` SIN `ca_bundle` y sin ningún test. Con
`STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED` en OFF volvía el bug entero: SSLError
contra un GitLab con certificado interno, con el bundle perfectamente configurado.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_mod                     # noqa: E402
from services import tracker_provider as tp     # noqa: E402


@pytest.fixture(autouse=True)
def gitlab_encendido(monkeypatch):
    monkeypatch.setattr(config_mod.config, "STACKY_GITLAB_ENABLED", True, raising=False)
    monkeypatch.setattr(tp, "resolve_project_context",
                        lambda project_name=None: SimpleNamespace(tracker_type="gitlab"))


@pytest.fixture()
def espia(monkeypatch):
    """Captura los kwargs con los que se construye el provider, sin red."""
    capturado: dict = {}

    class _ProviderFalso:
        def __init__(self, **kw):
            capturado.update(kw)

    import services.gitlab_provider as gp

    monkeypatch.setattr(gp, "GitLabTrackerProvider", _ProviderFalso)
    return capturado


def test_la_rama_legacy_recibe_el_bundle(monkeypatch, espia, tmp_path):
    """EL GATE CONTRA EL DEFECTO: hoy no pasa ca_bundle en absoluto."""
    bundle = tmp_path / "empresa.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n",
                      encoding="utf-8")
    monkeypatch.setattr(
        config_mod.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", False, raising=False
    )
    monkeypatch.setattr(config_mod.config, "STACKY_GITLAB_CA_BUNDLE", str(bundle), raising=False)

    tp.get_tracker_provider("RIPLEY")

    assert "ca_bundle" in espia, f"la rama legacy sigue sin cablear el bundle: {espia}"
    assert espia["ca_bundle"] == str(bundle)


def test_con_el_bundle_vacio_pasa_none(monkeypatch, espia):
    """Vacío ⇒ None (no ''), para que `crear_contexto_openssl` no monte adapter y la
    sesión siga por truststore."""
    monkeypatch.setattr(
        config_mod.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", False, raising=False
    )
    monkeypatch.setattr(config_mod.config, "STACKY_GITLAB_CA_BUNDLE", "", raising=False)

    tp.get_tracker_provider("RIPLEY")

    assert espia.get("ca_bundle") is None, f"ca_bundle={espia.get('ca_bundle')!r}"


def test_el_provider_por_proyecto_sigue_igual(monkeypatch, espia, tmp_path):
    """No se rompió la rama de hoy (la que SÍ andaba): sigue tomando el bundle del
    TrackerTarget del proyecto, no de la config global."""
    monkeypatch.setattr(
        config_mod.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", True, raising=False
    )
    del_proyecto = str(tmp_path / "del-proyecto.pem")
    import services.project_context as pc

    monkeypatch.setattr(pc, "build_tracker_target", lambda _p: SimpleNamespace(
        project_path="ripley/agenda-web", base_url="https://gl.interno",
        group="ripley", auth_path="auth/gitlab_auth.json", ca_bundle=del_proyecto,
    ))

    tp.get_tracker_provider("RIPLEY")

    assert espia["ca_bundle"] == del_proyecto
    assert espia["project"] == "ripley/agenda-web"
    assert espia["base_url"] == "https://gl.interno"
