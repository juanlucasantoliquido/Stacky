"""Plan 286 F2/F3/F4 — Los cuatro escritores rutean por el tracker EFECTIVO.

NO TOCA DB (plan §4.2) salvo por el import de `api.tickets` de F4, que esta
medido: importa en ~3,8 s y NO abre ni crea la base (SQLAlchemy no conecta al
importar `db`). NO TOCA RED: dobles y monkeypatch.

El ticket "mentiroso" de RIPLEY es el corazon del eje: `tracker_type` dice
'azure_devops' porque ese es el default del ORM (models.py:49), pero su proyecto
declara `gitlab`. Son 2 filas reales de 228 en la BD viva.
"""
from types import SimpleNamespace

import pytest

from services.project_context import _reset_memo_tracker_declarado


@pytest.fixture(autouse=True)
def _memo_limpio():
    """El memo de F1 es modulo-level: sin esto el orden de los tests decide."""
    _reset_memo_tracker_declarado()
    yield
    _reset_memo_tracker_declarado()


_MAPA = {"RIPLEY": "gitlab", "RSPACIFICO": "azure_devops"}


def _con_config(monkeypatch, mapa=None):
    llamadas = []

    def _fake(nombre):
        llamadas.append(nombre)
        tipo = (mapa or _MAPA).get((nombre or "").strip().upper())
        return {"issue_tracker": {"type": tipo}} if tipo else None

    monkeypatch.setattr("project_manager.get_project_config", _fake)
    return llamadas


def _ticket(tracker_type, stacky, *, ado_id=1378, project="ProyTracker"):
    return SimpleNamespace(
        id=7,
        ado_id=ado_id,
        tracker_type=tracker_type,
        project=project,
        stacky_project_name=stacky,
    )


def _ripley_mentiroso():
    """La fila real: columna 'azure_devops', proyecto GitLab."""
    return _ticket("azure_devops", "RIPLEY")


class _FakeProvider:
    name = "gitlab"

    def update_item_state(self, item_id, logical_state):
        return {"state": "closed"}

    def get_item(self, item_id):
        return {"state": "closed"}


class _FakeAdoClient:
    def update_work_item_state(self, ado_id, state):
        return {"ok": True}


@pytest.fixture
def ado_spy(monkeypatch):
    """Espia `build_ado_client` SIN construir un AdoClient real."""
    calls = []
    fake = _FakeAdoClient()

    def _fake_build(project_name=None, *, tracker_project=None, ticket=None):
        calls.append(project_name)
        return fake

    from services import project_context

    monkeypatch.setattr(project_context, "build_ado_client", _fake_build)
    return SimpleNamespace(calls=calls, client=fake)


@pytest.fixture
def provider_spy(monkeypatch):
    doble = _FakeProvider()
    from services import tracker_provider

    monkeypatch.setattr(tracker_provider, "get_tracker_provider", lambda p=None: doble)
    return doble


def _flag_off(monkeypatch):
    monkeypatch.setattr(
        "config.config.STACKY_TRACKER_ROUTING_STRICT_ENABLED", False, raising=False,
    )


# ── F2 — tracker_write_router (escritor de ESTADO) ───────────────────────────

def test_ticket_de_ripley_con_columna_mentirosa_resuelve_gitlab(
    monkeypatch, ado_spy, provider_spy
):
    """EL rojo primero de todo el eje. Con el codigo previo daba 'ado_client'."""
    _con_config(monkeypatch)
    from services import tracker_write_router as twr

    w = twr.resolve_state_writer(_ripley_mentiroso())
    assert w.kind == "provider"
    assert w.tracker_type == "gitlab"
    assert w.handle is provider_spy
    assert ado_spy.calls == [], (
        f"se construyo un cliente ADO para un ticket de GitLab: {ado_spy.calls}"
    )


def test_ticket_de_rspacifico_sigue_resolviendo_ado(monkeypatch, ado_spy):
    _con_config(monkeypatch)
    from services import tracker_write_router as twr

    w = twr.resolve_state_writer(_ticket("azure_devops", "RSPACIFICO"))
    assert w.kind == "ado_client"
    assert w.tracker_type == "azure_devops"


def test_ticket_sin_proyecto_sigue_resolviendo_ado(monkeypatch, ado_spy):
    """P3 — fail-closed. Comportamiento de HOY, conservado."""
    _con_config(monkeypatch)
    from services import tracker_write_router as twr

    w = twr.resolve_state_writer(_ticket("azure_devops", None))
    assert w.kind == "ado_client"


def test_ticket_sin_columna_en_proyecto_ado_resuelve_ado(monkeypatch, ado_spy):
    _con_config(monkeypatch)
    from services import tracker_write_router as twr

    w = twr.resolve_state_writer(_ticket(None, "RSPACIFICO"))
    assert w.kind == "ado_client"


def test_preview_reporta_el_tracker_efectivo(monkeypatch, ado_spy, provider_spy):
    """El dry-run le reportaba 'azure_devops' al operador para un ticket de
    RIPLEY. Pasa a reportar 'gitlab'."""
    _con_config(monkeypatch)
    from services import tracker_write_router as twr

    d = twr.preview_state_write(ticket=_ripley_mentiroso(), requested_state="Done")
    assert d["tracker_type"] == "gitlab"


def test_kill_switch_apagado_manda_el_ticket_mentiroso_a_ado(
    monkeypatch, ado_spy, provider_spy
):
    """P7 — rollback demostrado con una sola palanca."""
    _con_config(monkeypatch)
    _flag_off(monkeypatch)
    from services import tracker_write_router as twr

    w = twr.resolve_state_writer(_ripley_mentiroso())
    assert w.kind == "ado_client"
