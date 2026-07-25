"""tests/test_plan218_tracker_target.py -- Plan 218 F4.

Destino de tracker POR PROYECTO: fin del GitLab singleton global (bloqueo B1).
Sin esto no hay dos proyectos GitLab, ni coexistencia ADO+GitLab, ni migración
verificable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_module  # noqa: E402


def _cfg(**tracker):
    base = {"type": "gitlab", "project": "grupo/repo"}
    base.update(tracker)
    return {"name": "RSPACIFICO", "issue_tracker": base}


def _patch_cfg(cfg):
    """Dobla la LECTURA del config.json del proyecto (no el provider ni el módulo config)."""
    return patch("services.project_context.get_project_config", return_value=cfg)


def test_auth_path_gitlab_usa_su_propio_archivo():
    from services.project_context import _auth_path_for

    ruta = _auth_path_for(_cfg())

    assert ruta is not None
    assert ruta.replace("\\", "/").endswith("auth/gitlab_auth.json"), ruta
    assert "ado_auth.json" not in ruta


def test_target_toma_base_url_del_proyecto():
    from services.project_context import build_tracker_target

    with _patch_cfg(_cfg(base_url="https://git.interno/")):
        target = build_tracker_target("RSPACIFICO")

    assert target.base_url == "https://git.interno/"
    assert target.tracker_type == "gitlab"


def test_target_cae_a_config_global_si_falta(monkeypatch):
    from services.project_context import build_tracker_target

    monkeypatch.setattr(config_module.config, "GITLAB_URL", "https://gl.global")
    monkeypatch.setattr(config_module.config, "GITLAB_PROJECT", "global/proj")

    with _patch_cfg({"name": "RSPACIFICO", "issue_tracker": {"type": "gitlab"}}):
        target = build_tracker_target("RSPACIFICO")

    assert target.base_url == "https://gl.global"
    assert target.project_path == "global/proj"


def test_factory_pasa_project_path_no_nombre_stacky(monkeypatch):
    """B1: la fábrica pasaba el nombre STACKY ('RSPACIFICO') como path de proyecto GitLab."""
    import services.tracker_provider as tp

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_ENABLED", True)

    with _patch_cfg(_cfg(project="grupo/repo", base_url="https://git.interno")):
        provider = tp.get_tracker_provider("RSPACIFICO")

    assert provider._project == "grupo/repo"
    assert provider._project != "RSPACIFICO"


def test_dos_proyectos_gitlab_distintos(monkeypatch):
    """Dos proyectos GitLab con destinos distintos conviven en la MISMA corrida."""
    from services.gitlab_provider import GitLabTrackerProvider

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")

    uno = GitLabTrackerProvider(project="grupo-a/repo-a", base_url="https://gl-a.test")
    dos = GitLabTrackerProvider(project="grupo-b/repo-b", base_url="https://gl-b.test")

    assert uno._project == "grupo-a/repo-a"
    assert dos._project == "grupo-b/repo-b"
    assert uno._client._base_url == "https://gl-a.test"
    assert dos._client._base_url == "https://gl-b.test"


def test_flag_off_es_byte_identico(monkeypatch):
    """Con STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED=False vuelve la ruta legacy."""
    import services.tracker_provider as tp

    monkeypatch.setenv("GITLAB_TOKEN", "t0k3n-de-test")
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_ENABLED", True)
    monkeypatch.setattr(config_module.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", False)
    monkeypatch.setattr(config_module.config, "GITLAB_PROJECT", "")

    with _patch_cfg(_cfg(project="grupo/repo")):
        provider = tp.get_tracker_provider("RSPACIFICO")

    # Ruta legacy: se pasa el NOMBRE STACKY tal cual (el comportamiento previo al 218).
    assert provider._project == "RSPACIFICO"


def test_perfil_gitlab_existe_y_valida():
    ruta = _BACKEND / "services" / "client_profile_defaults" / "gitlab.json"
    ado = _BACKEND / "services" / "client_profile_defaults" / "azure_devops.json"

    assert ruta.exists(), "falta services/client_profile_defaults/gitlab.json"
    perfil = json.loads(ruta.read_text(encoding="utf-8"))
    perfil_ado = json.loads(ado.read_text(encoding="utf-8"))

    assert set(perfil) == set(perfil_ado), (
        f"claves de primer nivel distintas: solo en gitlab={set(perfil) - set(perfil_ado)}, "
        f"solo en ado={set(perfil_ado) - set(perfil)}"
    )
    assert perfil["language"]["ticket_token_pattern"] == "GL-{id}"
    estados = json.dumps(perfil["tracker_state_machine"], ensure_ascii=False)
    assert "stacky::" in estados, "los estados de GitLab son etiquetas stacky::*"


def test_ado_no_cambia(monkeypatch):
    """Regresión ADO: el destino de un proyecto Azure DevOps se resuelve igual que antes."""
    from services.project_context import build_tracker_target

    cfg = {
        "name": "RSPACIFICO",
        "issue_tracker": {
            "type": "azure_devops", "project": "Strategist_Pacifico",
            "organization": "UbimiaPacifico",
        },
    }
    with _patch_cfg(cfg):
        target = build_tracker_target("RSPACIFICO")

    assert target.tracker_type == "azure_devops"
    assert target.project_path == "Strategist_Pacifico"
    assert target.organization == "UbimiaPacifico"
    assert target.base_url is None
    assert (target.auth_path or "").replace("\\", "/").endswith("auth/ado_auth.json")
