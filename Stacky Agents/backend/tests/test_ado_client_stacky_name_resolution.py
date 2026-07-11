"""Fix "PRs no cargan" — _resolve_active_project_defaults debe aceptar el nombre
STACKY del proyecto (p.ej. "RSPACIFICO"), no solo el tracker_project de ADO
(p.ej. "Strategist_Pacifico").

Bug original: la API DevOps pasa el nombre Stacky; find_project_for_tracker no lo
matchea y devuelve (None, {}), que NO es None, así que el fallback al proyecto
activo se salteaba y el AdoClient quedaba sin auth del proyecto → AdoConfigError
→ 500 genérico en /api/pr-review/list.
"""
import os
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.ado_client import _resolve_active_project_defaults

_CFG = {
    "name": "RSPACIFICO",
    "issue_tracker": {
        "type": "azure_devops",
        "organization": "UbimiaPacifico",
        "project": "Strategist_Pacifico",
        "auth_file": "auth/ado_auth.json",
    },
}


def test_resolves_by_stacky_project_name():
    """project="RSPACIFICO" (nombre Stacky) → org/proyecto/auth del config del proyecto."""
    with mock.patch("project_manager.find_project_for_tracker", return_value=(None, {})), \
         mock.patch("project_manager.get_project_config", return_value=_CFG) as gpc, \
         mock.patch("project_manager.get_active_project", return_value=None):
        org, project, auth = _resolve_active_project_defaults(None, "RSPACIFICO", None)
    gpc.assert_called_once_with("RSPACIFICO")
    assert org == "UbimiaPacifico"
    assert project == "Strategist_Pacifico"
    assert auth and auth.replace("\\", "/").endswith("RSPACIFICO/auth/ado_auth.json")


def test_resolves_by_tracker_project_name_still_works():
    """project="Strategist_Pacifico" (nombre tracker) sigue resolviendo como antes."""
    with mock.patch("project_manager.find_project_for_tracker",
                    return_value=("RSPACIFICO", _CFG)) as fpt, \
         mock.patch("project_manager.get_active_project", return_value=None):
        org, project, auth = _resolve_active_project_defaults(None, "Strategist_Pacifico", None)
    fpt.assert_called_once_with("Strategist_Pacifico")
    assert org == "UbimiaPacifico"
    assert project == "Strategist_Pacifico"
    assert auth and "RSPACIFICO" in auth


def test_unknown_project_falls_back_to_active():
    """Nombre que no matchea nada → cae al proyecto activo (antes quedaba colgado en cfg={})."""
    def _gpc(name):
        return _CFG if name == "RSPACIFICO" else None

    with mock.patch("project_manager.find_project_for_tracker", return_value=(None, {})), \
         mock.patch("project_manager.get_project_config", side_effect=_gpc), \
         mock.patch("project_manager.get_active_project", return_value="RSPACIFICO"):
        org, project, auth = _resolve_active_project_defaults(None, "no-existe", None)
    assert org == "UbimiaPacifico"
    assert project == "Strategist_Pacifico"
    assert auth and "RSPACIFICO" in auth
