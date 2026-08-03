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

        # El mismo `session_scope` aislado que usa el sync. Se expone para que un
        # test pueda re-apuntar OTRO módulo que también lo importó por valor
        # (`api.tickets`), sin lo cual ese módulo escribiría en la BD del operador.
        scope = staticmethod(_scope_de_test)

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


# ── Casos 18-21: el publicador de épica y el sync tienen que hablar el MISMO ──
# idioma. Los dos escriben en `tickets`; si no coinciden en la terna, el issue
# entra DOS veces y el grafo muestra la épica duplicada.

_EPIC_HTML = "<h1>Épica de prueba</h1><h2>RF-001 — algo</h2><p>cuerpo</p>"


class _ProviderQueCrea:
    """Provider falso con la forma REAL de `GitLabTrackerProvider.create_item`:
    devuelve `_normalize_issue`, que estringa los ids (gitlab_provider.py:131-132)."""

    name = "gitlab"

    def __init__(self, issue):
        self._issue = issue
        self.creados = 0

    def create_item(self, item):
        self.creados += 1
        return dict(self._issue)

    def item_url(self, item_id):
        return f"https://gl.interno/ripley/agenda-web/-/issues/{item_id}"


def _publicar(monkeypatch, bd, issue):
    """Corre `_publish_epic_to_ado` con el provider GitLab contra la BD del test."""
    import api.tickets as t

    prov = _ProviderQueCrea(issue)
    monkeypatch.setattr(t, "_provider_for_ticket", lambda **kw: prov)
    monkeypatch.setattr(t, "session_scope", bd.scope)
    monkeypatch.setattr(t, "_epic_brief_save", lambda *a, **k: None)
    return t._publish_epic_to_ado(
        description_html=_EPIC_HTML, brief="brief", project_name="RIPLEY",
    ), prov


def test_18_el_id_publicado_es_int_y_es_el_iid(bd, monkeypatch):
    """El sello viaja a `metadata["epic_ado_id"]` y el modal lo lee con
    `typeof === "number"` (EpicFromBriefModal.tsx:223). Un str ahí significa que el
    guard NO reconoce la épica ya publicada y el frontend publica una SEGUNDA."""
    publicada, _ = _publicar(monkeypatch, bd, _issue(7, id_=4242))

    assert isinstance(publicada.ado_id, int), (
        f"el id publicado es {type(publicada.ado_id).__name__} "
        f"({publicada.ado_id!r}); el guard del modal solo acepta number"
    )
    assert publicada.ado_id == 7, "el número visible de GitLab es el iid, no el id global"


def test_19_la_fila_del_publicador_nace_con_la_terna_de_gitlab(bd, monkeypatch):
    """`tracker_type` NO puede quedar en el default `azure_devops` (models.py:49)
    dentro de un proyecto GitLab: el sync busca por la terna y no la encontraría."""
    from models import Ticket

    _publicar(monkeypatch, bd, _issue(7, id_=4242))

    fila = bd.session.query(Ticket).one()
    assert fila.tracker_type == "gitlab", (
        f"la fila quedó con tracker_type={fila.tracker_type!r}: el sync de GitLab "
        f"busca por (proyecto, 'gitlab', external_id) y va a dar de alta otra fila"
    )
    assert fila.external_id == 4242, "external_id es el id GLOBAL (gitlab_sync.py:144)"
    assert fila.ado_id == 7, "ado_id es el iid (gitlab_sync.py:145)"


def test_20_publicar_y_sincronizar_deja_UNA_fila_no_dos(bd, monkeypatch):
    """EL SÍNTOMA: 'creo una épica en el grafo y me la duplica'.

    Publicador y sync escriben en la misma tabla. Si no coinciden en la terna, el
    MISMO issue de GitLab entra dos veces y el grafo dibuja dos nodos."""
    from models import Ticket

    issue = _issue(7, id_=4242, titulo="Épica de prueba", tipo="Epic")
    _publicar(monkeypatch, bd, issue)
    res, _ = _sync(monkeypatch, [issue])

    filas = bd.session.query(Ticket).all()
    assert len(filas) == 1, (
        f"el issue de GitLab quedó {len(filas)} veces en la tabla: "
        f"{[(f.id, f.ado_id, f.external_id, f.tracker_type) for f in filas]}"
    )
    assert res["created"] == 0, "el sync dio de alta el issue que el publicador ya había creado"


def test_21_proyecto_ado_conserva_el_id_int_y_su_tracker_type(bd, monkeypatch):
    """Backward-compat: sin provider (camino ADO) nada cambia."""
    import api.tickets as t
    from models import Ticket

    monkeypatch.setattr(t, "_provider_for_ticket", lambda **kw: None)
    monkeypatch.setattr(t, "session_scope", bd.scope)
    monkeypatch.setattr(t, "_epic_brief_save", lambda *a, **k: None)

    class _Ado:
        def create_work_item(self, **kw):
            return {"id": 555, "rev": 1,
                    "fields": {"System.Title": "T"},
                    "_links": {"html": {"href": "https://dev.azure.com/wi/555"}}}

    monkeypatch.setattr(t, "_ado_client_for_ticket", lambda **kw: _Ado())

    publicada = t._publish_epic_to_ado(
        description_html=_EPIC_HTML, brief="b", project_name="ProyADO",
    )
    assert publicada.ado_id == 555 and isinstance(publicada.ado_id, int)
    fila = bd.session.query(Ticket).one()
    assert fila.tracker_type == "azure_devops" and fila.external_id == 555
