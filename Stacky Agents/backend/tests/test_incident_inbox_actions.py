"""tests/test_incident_inbox_actions.py -- Acciones desde la bandeja de incidencias.

Cubre la flag STACKY_INCIDENT_INBOX_ACTIONS_ENABLED, que levanta el guardarrail
de solo-lectura del Plan 238, y su exposicion en /api/incident-inbox/status.

A DIFERENCIA de test_plan238_inbox_flag.py, este archivo NO hace
importlib.reload(config): monkeypatchea el atributo sobre la instancia
`config.config` (que es lo que lee el codigo productivo). Asi puede convivir en
el mismo archivo con tests que levantan la app sin contaminar su binding de
config (ver gotcha-config-reload-harness-flags-contamina).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS  # noqa: E402

KEY = "STACKY_INCIDENT_INBOX_ACTIONS_ENABLED"
PARENT_KEY = "STACKY_INCIDENT_INBOX_ENABLED"


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


# ── Registro de la flag ──────────────────────────────────────────────────────

def test_flag_registrada_bool_default_on():
    spec = next((s for s in FLAG_REGISTRY if s.key == KEY), None)
    assert spec is not None, f"{KEY} no esta en FLAG_REGISTRY"
    assert spec.type == "bool"
    assert spec.default is True


def test_flag_declara_requires_al_padre():
    """La bandeja apagada implica acciones apagadas: la arista tiene que existir."""
    spec = next(s for s in FLAG_REGISTRY if s.key == KEY)
    assert spec.requires == PARENT_KEY


def test_flag_categorizada_interfaz_ui():
    assert KEY in _CATEGORY_KEYS["interfaz_ui"]


def test_flag_tiene_ayuda_llana():
    """Sin esto, test_harness_flags_help se pone rojo por culpa de esta flag."""
    from services.harness_flags_help import PLAIN_HELP
    assert KEY in PLAIN_HELP
    entry = PLAIN_HELP[KEY]
    assert entry.on_effect.startswith("Si ")
    assert entry.off_effect.startswith("Si ")
    assert 10 <= len(entry.what.strip()) <= 200


def test_config_expone_la_flag_con_default_on():
    from config import config as cfg
    assert os.getenv(KEY) is None, (
        f"{KEY} esta seteada en el entorno: este test mide el default de fabrica"
    )
    assert getattr(cfg, KEY) is True


# ── Resolvedor _actions_enabled ──────────────────────────────────────────────

def test_actions_enabled_true_por_default():
    from api.incident_inbox import _actions_enabled
    assert _actions_enabled() is True


def test_actions_enabled_false_con_su_flag_off(monkeypatch):
    from api.incident_inbox import _actions_enabled
    import config as config_module
    monkeypatch.setattr(config_module.config, KEY, False, raising=False)
    assert _actions_enabled() is False


def test_actions_enabled_false_si_el_padre_esta_off():
    """Herencia del `requires`: la hija ON no alcanza si la bandeja esta apagada."""
    from api.incident_inbox import _actions_enabled
    with patch("api.incident_inbox._enabled", return_value=False):
        assert _actions_enabled() is False


# ── Contrato del endpoint de status ──────────────────────────────────────────

def test_status_expone_actions_enabled(client):
    data = client.get("/api/incident-inbox/status").get_json()
    assert data["actions_enabled"] is True


def test_status_actions_enabled_false_con_flag_off(client, monkeypatch):
    import config as config_module
    monkeypatch.setattr(config_module.config, KEY, False, raising=False)
    data = client.get("/api/incident-inbox/status").get_json()
    assert data["actions_enabled"] is False
    # La bandeja sigue viva: apagar las acciones NO apaga la lectura.
    assert data["enabled"] is True


def test_status_actions_enabled_false_con_bandeja_off(client):
    with patch("api.incident_inbox._enabled", return_value=False):
        data = client.get("/api/incident-inbox/status").get_json()
    assert data["enabled"] is False
    assert data["actions_enabled"] is False


def test_status_no_pierde_las_keys_del_238(client):
    """Aditivo: un frontend viejo tiene que seguir leyendo lo mismo."""
    data = client.get("/api/incident-inbox/status").get_json()
    for k in ("ok", "enabled", "flag_enabled", "incident_types",
              "incident_types_source", "closed_states", "closed_states_source"):
        assert k in data, f"falta la key {k!r} del contrato del Plan 238"


# ── Seam de los endpoints que la bandeja va a consumir ───────────────────────

def test_seam_finish_work_y_run_incident_dev_existen():
    """Ratchet: la bandeja cierra/resuelve reusando ESTOS endpoints, no propios.

    Si alguno se renombra o se borra, los botones de la bandeja quedan mudos y
    esto se pone rojo antes que el smoke visual.
    """
    from app import create_app
    app = create_app()
    rutas = {
        (rule.rule, verbo)
        for rule in app.url_map.iter_rules()
        for verbo in rule.methods
    }
    assert ("/api/tickets/<int:ticket_id>/finish-work", "POST") in rutas
    assert ("/api/agents/run-incident-dev", "POST") in rutas
