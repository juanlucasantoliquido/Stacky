"""tests/test_plan276_gitlab_sync.py — Plan 276 F5.

El sync GitLab → BD, que es LO ÚNICO que puede hacer que el grafo deje de estar
vacío. Los tres puntos que un implementador va a errar si no los lee, cada uno con
su gate corrido CONTRA el defecto:

- La CLAVE DE UPSERT es la terna (stacky_project_name, tracker_type, external_id),
  NUNCA `ado_id` (casos 14, 15, 16).
- Un ctx GitLab con `STACKY_GITLAB_ENABLED=false` NO puede terminar en un error de
  Azure DevOps (caso 13).
- La flag de sync apagada levanta `CapabilityUnavailable`, no `AdoConfigError`
  (caso 12).
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def bd(tmp_path, monkeypatch):
    """BD en un sqlite temporal, aislada de la del operador.

    P2-6: `DATABASE_URL` se setea ANTES de tocar `db`/`create_app`, porque
    `create_all` sin ella corre contra la BD REAL del operador (181 MB).
    `db.py` construye el engine al IMPORTARSE, así que hay que reimportarlo con la
    variable ya puesta o el engine apunta a la base de siempre.
    """
    from contextlib import contextmanager

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'plan276.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")

    from db import Base

    # `models` ANTES de create_all: es su import el que registra las tablas en
    # Base.metadata. Sin esta línea, create_all no crea nada y el primer test del
    # archivo muere con "no such table: tickets" (los demás pasan de casualidad,
    # porque otro test ya importó models — un falso verde por orden de ejecución).
    import models  # noqa: F401

    ruta = (tmp_path / "plan276.db").as_posix()
    motor = create_engine(f"sqlite:///{ruta}", future=True)
    Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(motor)
    assert tmp_path.name in str(motor.url), f"la BD del test NO está aislada: {motor.url}"

    @contextmanager
    def _scope_de_test():
        s = Sesion()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # `services.gitlab_sync` importó `session_scope` POR VALOR (`from db import
    # session_scope`), así que hay que re-apuntarlo acá: parchear `db.session_scope`
    # no tendría efecto y el sync escribiría en la BD real del operador.
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "session_scope", _scope_de_test)

    class _BD:
        """Fachada mínima para los asserts. `expire_all()` en cada acceso: el sync
        commitea en OTRA sesión, así que sin eso los reads vendrían del
        identity-map viejo y un test podría pasar mirando datos rancios."""

        def __init__(self):
            self._s = Sesion()

        @property
        def session(self):
            self._s.expire_all()
            return self._s

    fachada = _BD()
    yield fachada
    fachada._s.close()
    motor.dispose()


CTX = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="ripley/agenda-web",
    tracker_type="gitlab",
)


class _ProviderFalso:
    name = "gitlab"

    def __init__(self, items):
        self._items = items
        self.queries = []

    def fetch_open_items(self, query):
        self.queries.append(query)
        return list(self._items)


def _issue(iid, id_=None, titulo="T", tipo="Issue", parent=None, estado="opened"):
    return {
        "id": str(id_ if id_ is not None else 1000 + int(iid)),
        "iid": str(iid),
        "title": titulo,
        "description": "d",
        "state": estado,
        "labels": [f"type::{tipo.lower()}"] if tipo != "Issue" else [],
        "assignees": [],
        "web_url": f"https://gl.interno/ripley/agenda-web/-/issues/{iid}",
        "updated_at": "2026-07-31T00:00:00Z",
        "work_item_type": tipo,
        "parent": str(parent) if parent is not None else None,
    }


def _sync(monkeypatch, items, ctx=CTX):
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "resolve_project_context", lambda _p: ctx)
    prov = _ProviderFalso(items)
    return gs.sync_gitlab_tickets("RIPLEY", provider=prov), prov


# ── Casos 1-11: el mapeo, la idempotencia y los casos borde ──────────────────

def test_01_tres_issues_dan_tres_filas_con_el_mapeo_completo(bd, monkeypatch):
    from models import Ticket

    res, _ = _sync(monkeypatch, [_issue(1), _issue(2), _issue(3)])
    assert res["fetched"] == 3 and res["created"] == 3
    filas = bd.session.query(Ticket).filter(Ticket.tracker_type == "gitlab").all()
    assert len(filas) == 3
    f = bd.session.query(Ticket).filter(Ticket.external_id == 1001).one()
    assert f.ado_id == 1                              # iid, el número visible
    assert f.external_id == 1001                      # id global de GitLab
    assert f.project == "ripley/agenda-web"            # tracker_project
    assert f.stacky_project_name == "RIPLEY"
    assert f.tracker_type == "gitlab"
    assert f.ado_state == "opened"
    assert f.ado_url.endswith("/issues/1")
    assert f.last_synced_at is not None


def test_02_iid_no_numerico_se_saltea_y_el_resto_se_guarda(bd, monkeypatch):
    from models import Ticket

    malo = _issue(1)
    malo["iid"] = "no-es-un-numero"
    res, _ = _sync(monkeypatch, [malo, _issue(2)])
    assert res["skipped"] == 1, res
    assert res["created"] == 1, "el issue sano tiene que guardarse igual"
    assert bd.session.query(Ticket).count() == 1


def test_03_segunda_corrida_identica_es_idempotente(bd, monkeypatch):
    items = [_issue(1), _issue(2)]
    primera, _ = _sync(monkeypatch, items)
    assert primera["created"] == 2
    segunda, _ = _sync(monkeypatch, items)
    assert segunda["created"] == 0 and segunda["updated"] == 0 and segunda["removed"] == 0, segunda


def test_04_cambio_de_titulo_cuenta_como_updated(bd, monkeypatch):
    from models import Ticket

    _sync(monkeypatch, [_issue(1, titulo="viejo")])
    res, _ = _sync(monkeypatch, [_issue(1, titulo="nuevo")])
    assert res["updated"] == 1 and res["created"] == 0
    assert bd.session.query(Ticket).one().title == "nuevo"


def test_05_issue_que_desaparece_se_marca_cerrado_y_la_fila_sigue(bd, monkeypatch):
    from models import Ticket

    _sync(monkeypatch, [_issue(1), _issue(2)])
    res, _ = _sync(monkeypatch, [_issue(1)])
    assert res["removed"] == 1, res
    # NUNCA se borra: riel del producto.
    assert bd.session.query(Ticket).count() == 2, "el sync BORRÓ una fila del operador"
    ido = bd.session.query(Ticket).filter(Ticket.external_id == 1002).one()
    assert ido.ado_state == "closed"


def test_06_type_epic_da_work_item_type_epic(bd, monkeypatch):
    from models import Ticket

    _sync(monkeypatch, [_issue(1, tipo="Epic")])
    assert bd.session.query(Ticket).one().work_item_type == "Epic"


def test_07_sin_label_de_tipo_cae_a_issue(bd, monkeypatch):
    from models import Ticket

    sin_tipo = _issue(1)
    sin_tipo.pop("work_item_type")
    _sync(monkeypatch, [sin_tipo])
    assert bd.session.query(Ticket).one().work_item_type == "Issue"


def test_08_parent_con_iid_da_parent_ado_id_int(bd, monkeypatch):
    from models import Ticket

    _sync(monkeypatch, [_issue(5, parent=3)])
    f = bd.session.query(Ticket).one()
    assert f.parent_ado_id == 3 and isinstance(f.parent_ado_id, int)


def test_09_parent_vacio_da_none(bd, monkeypatch):
    from models import Ticket

    _sync(monkeypatch, [_issue(5, parent=None)])
    assert bd.session.query(Ticket).one().parent_ado_id is None


def test_10_titulo_de_900_chars_se_trunca_a_500(bd, monkeypatch):
    from models import Ticket

    _sync(monkeypatch, [_issue(1, titulo="x" * 900)])
    assert len(bd.session.query(Ticket).one().title) == 500


def test_11_la_query_es_de_abiertos(bd, monkeypatch):
    """La semántica de `removed` (lo que no vino pasa a closed) SOLO es correcta
    si la query es de abiertos. Si alguien la cambia, este test se pone rojo."""
    _, prov = _sync(monkeypatch, [_issue(1)])
    assert prov.queries and prov.queries[0].state == "open", prov.queries


# ── Casos 12-16: los gates de la v2 (C1, C2, C9) ─────────────────────────────

def _rutear(monkeypatch, ctx, *, provider_resuelto=None, error_fabrica=None):
    """Ejercita `_sync_via_provider_or_ado`, que es donde vive el ruteo."""
    import api.tickets as t

    monkeypatch.setattr(t, "_provider_for_ticket", lambda **kw: None)
    monkeypatch.setattr(t, "resolve_project_context", lambda _p: ctx)

    def _fabrica(_p):
        if error_fabrica is not None:
            raise error_fabrica
        return provider_resuelto

    monkeypatch.setattr(t, "get_tracker_provider", _fabrica)
    return t._sync_via_provider_or_ado("RIPLEY")


def test_12_flag_de_sync_off_levanta_capability_unavailable(bd, monkeypatch):
    """C9 — en el v1 este caso era INSATISFACIBLE: con la flag de sync OFF el
    provider ni se resolvía y el flujo terminaba en AdoConfigError."""
    import config as cmod
    from services.ado_client import AdoConfigError
    from services.tracker_provider import CapabilityUnavailable

    monkeypatch.setattr(cmod.config, "STACKY_GITLAB_SYNC_ENABLED", False, raising=False)
    with pytest.raises(CapabilityUnavailable) as exc_info:
        _rutear(monkeypatch, CTX, provider_resuelto=_ProviderFalso([]))
    assert not isinstance(exc_info.value, AdoConfigError), (
        "una flag de GitLab apagada NO puede reportarse como un error de Azure DevOps"
    )


def test_13_master_switch_apagado_nombra_el_switch_y_no_es_error_de_ado(bd, monkeypatch):
    """C1 — EL DEFECTO BLOQUEANTE DEL v1. Hoy esto daba
    AdoConfigError('El proyecto no usa Azure DevOps') ⇒ 400 nombrando el
    proveedor equivocado. Se assertea la SUBCADENA del mensaje: un
    TrackerConfigError genérico que no nombra el switch deja al operador igual
    de perdido."""
    from services.ado_client import AdoConfigError
    from services.tracker_provider import TrackerConfigError

    with pytest.raises(TrackerConfigError) as exc_info:
        _rutear(
            monkeypatch, CTX,
            error_fabrica=TrackerConfigError(
                "GitLab deshabilitado (STACKY_GITLAB_ENABLED=false)"
            ),
        )
    assert "STACKY_GITLAB_ENABLED" in str(exc_info.value), (
        f"el error no nombra el master switch: {exc_info.value}"
    )
    assert not isinstance(exc_info.value, AdoConfigError)


def test_14_segunda_corrida_no_viola_el_indice_unico(bd, monkeypatch):
    """C2 — el gate de la clave de upsert. Los TRES asserts juntos: (a) sola pasa
    si se hicieron duplicados; (b) sola pasa si el sync no escribió nada."""
    from models import Ticket

    items = [_issue(1), _issue(2), _issue(3)]
    _sync(monkeypatch, items)
    cuenta_1 = bd.session.query(Ticket).count()
    res2, _ = _sync(monkeypatch, items)          # (a) no levanta IntegrityError
    assert bd.session.query(Ticket).count() == cuenta_1 == 3   # (b) mismo conteo
    assert res2["created"] == 0                                # (c) no creó nada


def test_15_issue_sin_id_no_deja_filas_con_external_id_null(bd, monkeypatch):
    """C2 — un external_id=None insertado hoy hace explotar la corrida de mañana
    contra el índice único."""
    from models import Ticket

    sin_id = _issue(1)
    sin_id["id"] = ""
    res, _ = _sync(monkeypatch, [sin_id, _issue(2)])
    assert res["skipped"] == 1
    assert bd.session.query(Ticket).filter(
        Ticket.external_id.is_(None), Ticket.tracker_type == "gitlab"
    ).count() == 0


def test_16_el_upsert_machea_por_la_terna_no_por_ado_id(bd, monkeypatch):
    """C2 — construido para FALLAR si alguien upsertea por `ado_id`: sembramos una
    fila con el MISMO ado_id y distinto external_id. Son issues distintos."""
    from models import Ticket

    bd.session.add(Ticket(
        ado_id=1, external_id=9999, project="ripley/agenda-web",
        stacky_project_name="RIPLEY", tracker_type="gitlab",
        title="sembrada a mano", ado_state="opened",
    ))
    bd.session.commit()

    _sync(monkeypatch, [_issue(1)])          # mismo iid=1 ⇒ mismo ado_id, otro id

    filas = bd.session.query(Ticket).filter(Ticket.tracker_type == "gitlab").all()
    assert len(filas) == 2, (
        f"se upserteó por ado_id y se pisó un issue distinto: "
        f"{[(f.ado_id, f.external_id, f.title) for f in filas]}"
    )
    sembrada = bd.session.query(Ticket).filter(Ticket.external_id == 9999).one()
    assert sembrada.title == "sembrada a mano", "la fila sembrada se pisó"


def test_17_proyecto_ado_no_ejecuta_el_bloque_nuevo(bd, monkeypatch):
    """Backward-compat: para azure_devops el bloque nuevo no corre ni una línea
    (gate de que `get_tracker_provider` NO se llama)."""
    import api.tickets as t

    llamadas = []
    monkeypatch.setattr(t, "_provider_for_ticket", lambda **kw: None)
    monkeypatch.setattr(
        t, "resolve_project_context",
        lambda _p: SimpleNamespace(tracker_type="azure_devops", stacky_project_name="P",
                                   tracker_project="P"),
    )
    monkeypatch.setattr(t, "get_tracker_provider", lambda _p: llamadas.append("x"))
    monkeypatch.setattr(t, "_ado_client_for_ticket", lambda **kw: object())
    monkeypatch.setattr(t, "sync_tickets", lambda **kw: {"fetched": 0, "created": 0,
                                                        "updated": 0, "removed": 0})
    t._sync_via_provider_or_ado("P")
    assert llamadas == [], "para un proyecto ADO se resolvió un provider de tracker"
