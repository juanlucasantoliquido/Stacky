"""Plan 270 F1 + F7 — Tests del enrutador de escritura de estado.

NO TOCA DB: los tickets son SimpleNamespace. NO TOCA RED: dobles y monkeypatch.
14 casos: 10 de F1 (destino) + 4 de F7 (preview sin escribir).
"""
import pathlib
import re
import sys
from types import SimpleNamespace

import pytest

from services import tracker_write_router as twr
from services.tracker_provider import CapabilityUnavailable, TrackerConfigError

CAP = "tracker.items.update_state"


def _ticket(tracker_type, *, ado_id=101, project="ProyTracker", stacky="MiProy"):
    return SimpleNamespace(
        id=7,
        ado_id=ado_id,
        tracker_type=tracker_type,
        project=project,
        stacky_project_name=stacky,
    )


class _FakeProvider:
    """Doble del TrackerProvider que CUENTA escrituras (nunca hace red)."""

    name = "gitlab"

    def __init__(self):
        self.state_calls = []

    def update_item_state(self, item_id, logical_state):
        self.state_calls.append((item_id, logical_state))
        return {"state": "closed"}

    def get_item(self, item_id):
        return {"state": "closed"}


class _FakeAdoClient:
    def __init__(self):
        self.state_calls = []

    def update_work_item_state(self, ado_id, state):
        self.state_calls.append((ado_id, state))
        return {"ok": True}


@pytest.fixture
def ado_client_spy(monkeypatch):
    """Espia build_ado_client SIN construir un AdoClient real."""
    calls = []
    fake = _FakeAdoClient()

    def _fake_build(project_name=None, *, tracker_project=None, ticket=None):
        calls.append({
            "project_name": project_name,
            "tracker_project": tracker_project,
            "ticket": ticket,
        })
        return fake

    from services import project_context

    monkeypatch.setattr(project_context, "build_ado_client", _fake_build)
    return SimpleNamespace(calls=calls, client=fake)


# ── F1 — destino ──────────────────────────────────────────────────────────────

def test_1_ado_resuelve_a_cliente_ado(ado_client_spy):
    w = twr.resolve_state_writer(_ticket("azure_devops"))
    assert w.kind == "ado_client"
    assert w.tracker_type == "azure_devops"
    assert w.handle is ado_client_spy.client


def test_2_tracker_type_none_resuelve_a_cliente_ado(ado_client_spy):
    w = twr.resolve_state_writer(_ticket(None))
    assert w.kind == "ado_client"
    assert w.tracker_type == "azure_devops"


def test_3_gitlab_resuelve_al_provider(monkeypatch):
    doble = _FakeProvider()
    from services import tracker_provider

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda p=None: doble)
    w = twr.resolve_state_writer(_ticket("gitlab"))
    assert w.kind == "provider"
    assert w.handle is doble
    assert w.tracker_type == "gitlab"


def test_4_gitlab_sin_flag_del_adapter_levanta_capability_unavailable(monkeypatch):
    from services import tracker_provider

    def _boom(p=None):
        raise TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _boom)
    with pytest.raises(CapabilityUnavailable) as exc:
        twr.resolve_state_writer(_ticket("gitlab"))
    assert exc.value.provider == "gitlab"
    assert exc.value.capability == CAP


def test_5_tracker_desconocido_levanta_capability_unavailable():
    with pytest.raises(CapabilityUnavailable) as exc:
        twr.resolve_state_writer(_ticket("jira"))
    assert exc.value.provider == "jira"
    assert "jira" in exc.value.reason


def test_6_centinela_anti_fallback_ningun_tracker_no_ado_cae_al_cliente_ado(monkeypatch):
    """El corazon de F1: un ticket no-ADO NUNCA puede resolver a kind=ado_client."""
    from services import tracker_provider

    def _boom(p=None):
        raise TrackerConfigError("no configurado")

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _boom)
    for ttype in ("gitlab", "jira", "mantis"):
        try:
            w = twr.resolve_state_writer(_ticket(ttype))
        except CapabilityUnavailable:
            continue
        assert w.kind != "ado_client", f"{ttype} cayo al cliente ADO"


def test_7_routing_enabled_respeta_la_flag_apagada(monkeypatch):
    from config import config as cfg

    assert twr.routing_enabled() is True
    monkeypatch.setattr(cfg, "STACKY_TRACKER_STATE_WRITE_ROUTING_ENABLED", False)
    assert twr.routing_enabled() is False


def test_8_el_workaround_nombra_la_flag_literal_del_adapter(monkeypatch):
    """C4 — el operador tiene que poder actuar sin abrir el codigo."""
    from services import tracker_provider

    def _boom(p=None):
        raise TrackerConfigError("STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _boom)
    with pytest.raises(CapabilityUnavailable) as exc:
        twr.resolve_state_writer(_ticket("gitlab"))
    payload = exc.value.to_payload()
    assert payload["available"] is False
    assert payload["reason"]
    assert "STACKY_GITLAB_ENABLED" in payload["workaround"]


def test_9_centinela_anti_acoplamiento_services_no_importa_api():
    """C5 — un modulo de services/ no puede arrastrar api/tickets.py.

    Regla del repo escrita en services/completion_sync.py:93-95.
    """
    here = pathlib.Path(twr.__file__)
    src = here.read_text(encoding="utf-8", errors="replace")
    ofensores = re.findall(r"api\.tickets|from api\b|import api\b", src)
    assert ofensores == [], f"acoplamiento service->api: {ofensores}"
    # Segunda asercion: importar el router no debe traer api.tickets consigo.
    if "api.tickets" not in sys.modules:
        import importlib

        importlib.reload(twr)
        assert "api.tickets" not in sys.modules


def test_10_el_cliente_ado_se_construye_con_los_tres_kwargs_canonicos(ado_client_spy):
    """Mismos 3 kwargs que api/tickets.py:359-364, sin importar api/."""
    t = _ticket("azure_devops", project="ProyADO", stacky="StackyProy")
    twr.resolve_state_writer(t)
    assert len(ado_client_spy.calls) == 1
    call = ado_client_spy.calls[0]
    assert call["project_name"] == "StackyProy"
    assert call["tracker_project"] == "ProyADO"
    assert call["ticket"] is t


# ── F7 — preview sin escribir ─────────────────────────────────────────────────

def test_11_preview_ticket_ado(ado_client_spy):
    d = twr.preview_state_write(ticket=_ticket("azure_devops"), requested_state="Done")
    assert d["resolved"] is True
    assert d["tracker_type"] == "azure_devops"
    assert d["native_state"] == "Done"
    assert d["closes"] is True
    assert d["reason"] == "ok"


def test_12_preview_gitlab_sin_flag_devuelve_workaround(monkeypatch):
    from services import tracker_provider

    def _boom(p=None):
        raise TrackerConfigError("STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _boom)
    d = twr.preview_state_write(ticket=_ticket("gitlab"), requested_state="Done")
    assert d["resolved"] is False
    assert "STACKY_GITLAB_ENABLED" in d["workaround"]


def test_13_preview_estado_no_mapeable(monkeypatch):
    doble = _FakeProvider()
    from services import tracker_provider

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda p=None: doble)
    d = twr.preview_state_write(ticket=_ticket("gitlab"), requested_state="Cualquier Cosa")
    assert d["resolved"] is False
    assert d["reason"].startswith("unmappable_state:")


def test_14_centinela_de_no_escritura_preview_jamas_escribe(monkeypatch, ado_client_spy):
    """El corazon de F7: los 3 escenarios juntos hacen CERO escrituras."""
    doble = _FakeProvider()
    from services import tracker_provider

    # (a) ADO
    twr.preview_state_write(ticket=_ticket("azure_devops"), requested_state="Done")
    # (b) GitLab con destino no disponible
    def _boom(p=None):
        raise TrackerConfigError("STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", _boom)
    twr.preview_state_write(ticket=_ticket("gitlab"), requested_state="Done")
    # (c) GitLab con estado no mapeable
    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda p=None: doble)
    twr.preview_state_write(ticket=_ticket("gitlab"), requested_state="Cualquier Cosa")

    assert doble.state_calls == []
    assert ado_client_spy.client.state_calls == []
