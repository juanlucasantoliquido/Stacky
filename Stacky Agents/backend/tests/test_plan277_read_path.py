"""tests/test_plan277_read_path.py — Plan 277 F2. El read path consume el contrato.

QUÉ PRUEBA ESTE ARCHIVO, en una línea: que el ticket empieza a saber QUÉ ES y DE
QUIÉN CUELGA, y que apagar la flag lo devuelve exacto al comportamiento del 276.

Los payloads se arman con la FORMA LITERAL de la API de GitLab
(`{"id","iid","labels":[...],"epic":{...},"type":...}`) y pasan por
`GitLabTrackerProvider._normalize_issue` de verdad — no por diccionarios
inventados. Un test que fabrica el shape que quiere leer no prueba el read path,
prueba su propia fixture (§3.4).

Los asserts de ausencia siembran primero el caso positivo. `assert 43 not in ids`
también pasa cuando el catálogo quedó vacío por otro motivo; el gate real es
"la épica legítima entró Y el hijo no" en el MISMO test (caso 13).
"""
from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


CTX = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="ripley/agenda-web",
    tracker_type="gitlab",
)


@pytest.fixture()
def bd(tmp_path, monkeypatch):
    """BD en un sqlite temporal, aislada de la del operador (fixture del 276 F5).

    `DATABASE_URL` se setea ANTES de tocar `db`, porque `create_all` sin ella corre
    contra la BD REAL del operador (181 MB). Y `services.gitlab_sync` importó
    `session_scope` POR VALOR, así que hay que re-apuntarlo en el módulo: parchear
    `db.session_scope` no tendría efecto y el sync escribiría en la base viva.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'plan277.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")

    from db import Base

    import models  # noqa: F401  — su import es el que registra las tablas en Base.metadata

    ruta = (tmp_path / "plan277.db").as_posix()
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

    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "session_scope", _scope_de_test)

    class _BD:
        """`expire_all()` en cada acceso: el sync commitea en OTRA sesión, así que
        sin eso los reads vendrían del identity-map viejo y un test podría pasar
        mirando datos rancios."""

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


def _provider():
    """GitLabTrackerProvider real con el TRANSPORTE mockeado — cero red.

    `_normalize_issue` no toca el cliente, pero se construye el provider entero a
    propósito: si mañana la normalización empezara a hacer un request, este test
    lo mostraría en vez de esconderlo detrás de un objeto sintético.
    """
    import config as config_module
    from services.gitlab_provider import GitLabTrackerProvider

    with patch("services.gitlab_provider.GitLabClient") as mock_cls, \
         patch.object(config_module.config, "GITLAB_URL", "https://gl.interno"), \
         patch.object(config_module.config, "GITLAB_PROJECT", "ripley/agenda-web"), \
         patch.object(config_module.config, "STACKY_GITLAB_GROUP", ""), \
         patch.object(config_module.config, "STACKY_GITLAB_EPICS_NATIVE", False):
        cliente = MagicMock()
        cliente._project_path.return_value = "ripley/agenda-web"
        mock_cls.return_value = cliente
        return GitLabTrackerProvider(project="ripley/agenda-web")


def _payload(iid, *, labels=None, epic=None, tipo_nativo=None, titulo="T", id_=None):
    """La forma LITERAL de un issue de la API v4 de GitLab."""
    body = {
        "id": id_ if id_ is not None else 1000 + iid,
        "iid": iid,
        "title": titulo,
        "description": "<p>d</p>",
        "state": "opened",
        "labels": list(labels or []),
        "assignees": [{"username": "dev1"}],
        "web_url": f"https://gl.interno/ripley/agenda-web/-/issues/{iid}",
        "updated_at": "2026-07-31T00:00:00Z",
    }
    if epic is not None:
        body["epic"] = epic
    if tipo_nativo is not None:
        body["type"] = tipo_nativo
    return body


def _sync(monkeypatch, items, ctx=CTX):
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "resolve_project_context", lambda _p: ctx)

    class _ProviderFalso:
        name = "gitlab"

        def fetch_open_items(self, query):
            return list(items)

    return gs.sync_gitlab_tickets("RIPLEY", provider=_ProviderFalso())


# ── Casos 1-6: `_normalize_issue` clasifica con el contrato ──────────────────

def test_01_epica_de_ce_sin_epic_nativo_da_epic_y_sin_padre():
    """El caso de la épica *"Violeta Lugo"*: GitLab CE no manda `epic`, y la única
    señal de que es una épica es la etiqueta."""
    salida = _provider()._normalize_issue(_payload(7, labels=["type::epic"]))
    assert salida["work_item_type"] == "Epic"
    assert salida["parent"] is None
    assert salida["origen_tipo"] == "label"
    assert salida["origen_padre"] == "ninguno"


def test_02_hijo_de_ce_con_tipo_y_padre_por_etiqueta():
    salida = _provider()._normalize_issue(
        _payload(13, labels=["type::funcional", "epic::42"])
    )
    assert (salida["work_item_type"], salida["parent"]) == ("Funcional", 42)
    assert isinstance(salida["parent"], int), (
        "`parent` tiene que ser int|None (antes era str|None): es el cambio de tipo "
        "declarado en §3.2, y `_a_int` en el sync lo tolera pero nadie lo fijaba"
    )
    assert salida["origen_padre"] == "label"


def test_03_issue_sin_ninguna_etiqueta_no_empeora():
    """El estado real de los 53 issues de RIPLEY medido en F0: cero etiquetas.
    Backward-compat — el plan no puede degradar lo que ya funcionaba."""
    salida = _provider()._normalize_issue(_payload(1, labels=[]))
    assert (salida["work_item_type"], salida["parent"]) == ("Issue", None)
    assert salida["origen_tipo"] == "defecto"


def test_04_el_epic_nativo_de_premium_no_contamina_el_padre():
    """§3.2 — el iid del epic vive en el namespace del GRUPO y `parent_ado_id` se
    compara contra `Ticket.ado_id`, que lleva el iid del PROYECTO. Copiarlo daba un
    padre que nunca resolvía y tapaba la causa real."""
    salida = _provider()._normalize_issue(
        _payload(20, labels=["type::tecnico"], epic={"id": 5, "iid": 9})
    )
    assert salida["parent"] is None
    assert salida["parent_native_epic_iid"] == 9, (
        "el epic nativo tampoco puede perderse: se conserva aparte para diagnóstico"
    )


def test_05_dos_etiquetas_de_tipo_clasifican_igual_en_cualquier_orden():
    """El determinismo. `gitlab_provider` tomaba "la primera del array" y el orden
    de `labels` que devuelve la API no está garantizado: dos corridas idénticas
    podían clasificar distinto."""
    prov = _provider()
    directo = prov._normalize_issue(_payload(30, labels=["type::tecnico", "type::epic"]))
    invertido = prov._normalize_issue(_payload(30, labels=["type::epic", "type::tecnico"]))
    assert directo["work_item_type"] == invertido["work_item_type"]
    # Y no es un empate trivial: el ganador está DEFINIDO (menor alfabético).
    assert directo["work_item_type"] == "Epic", directo


def test_06_el_aviso_del_contrato_llega_al_log_con_el_iid(caplog):
    """Que el multi-tipo no sea silencioso. Sin este log, un issue mal etiquetado
    se clasifica "bien" para siempre y nadie se entera."""
    prov = _provider()

    # SEMBRADO: un payload SIN ambigüedad no puede emitir warnings. Sin esto, el
    # assert de abajo también pasaría si el provider logueara en cada issue.
    with caplog.at_level(logging.WARNING, logger="services.gitlab_provider"):
        prov._normalize_issue(_payload(11, labels=["type::bug"]))
    assert [r for r in caplog.records if "Plan 277" in r.getMessage()] == []

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="services.gitlab_provider"):
        prov._normalize_issue(_payload(77, labels=["type::tecnico", "type::epic"]))
    mensajes = [r.getMessage() for r in caplog.records]
    assert any("multi-tipo" in m for m in mensajes), mensajes
    assert any("iid=77" in m for m in mensajes), (
        f"el aviso no identifica QUÉ issue lo produjo: {mensajes}"
    )


# ── Caso 7: el migrador deja de tener regla propia ───────────────────────────

def test_07_el_migrador_ya_no_pierde_los_tipos_con_espacio():
    from services.migrator_verify import _infer_type_from_labels

    # SEMBRADO: el caso que la regex vieja SÍ resolvía tiene que seguir resolviendo,
    # o el test no distingue "arreglado" de "roto de otra forma".
    assert _infer_type_from_labels(["type::epic"]) == "Epic"

    salida = _infer_type_from_labels(["type::user story"])
    assert salida is not None, (
        "la regex `type::(\\w+)` no matchea espacios y devolvía None justo para lo "
        "que `create_item` escribía cuando el item_type tenía uno"
    )
    assert salida == "User Story"


# ── Casos 8-10: el sync, el cambio de tipo y la flag como kill-switch real ───

def test_08_el_sync_escribe_parent_ado_id_int_y_none(bd, monkeypatch):
    from models import Ticket

    prov = _provider()
    hijo = prov._normalize_issue(_payload(5, labels=["epic::3"]))
    suelto = prov._normalize_issue(_payload(6, labels=[]))
    assert isinstance(hijo["parent"], int), "el payload del test no ejercita el cambio de tipo"

    _sync(monkeypatch, [hijo, suelto])

    con_padre = bd.session.query(Ticket).filter(Ticket.ado_id == 5).one()
    sin_padre = bd.session.query(Ticket).filter(Ticket.ado_id == 6).one()
    assert con_padre.parent_ado_id == 3 and isinstance(con_padre.parent_ado_id, int)
    assert sin_padre.parent_ado_id is None


def test_09_la_flag_apagada_apaga_el_padre_aunque_la_etiqueta_este(bd, monkeypatch):
    """Que la flag sea un kill-switch REAL y no una flag registrada pero muerta.
    El gate corre contra el defecto: el item SÍ trae `epic::3`."""
    import config as cmod
    from models import Ticket

    hijo = _provider()._normalize_issue(_payload(5, labels=["type::funcional", "epic::3"]))
    assert hijo["parent"] == 3, "sin padre en el payload este test no probaría nada"

    monkeypatch.setattr(
        cmod.config, "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED", False, raising=False
    )
    _sync(monkeypatch, [hijo])

    assert bd.session.query(Ticket).one().parent_ado_id is None, (
        "la flag está registrada pero no gatea nada: el rollback sería ficticio"
    )


def test_10_la_flag_gatea_el_padre_pero_nunca_el_tipo(bd, monkeypatch):
    """`work_item_type` ya lo poblaba el plan 276: apagarlo sería una REGRESIÓN,
    no un rollback. La flag solo puede apagar lo que este plan agrega."""
    import config as cmod
    from models import Ticket

    hijo = _provider()._normalize_issue(_payload(5, labels=["type::funcional", "epic::3"]))
    monkeypatch.setattr(
        cmod.config, "STACKY_GITLAB_HIERARCHY_CONTRACT_ENABLED", False, raising=False
    )
    _sync(monkeypatch, [hijo])

    fila = bd.session.query(Ticket).one()
    assert fila.work_item_type == "Funcional", "la flag degradó el tipo: eso es 276, no 277"
    assert fila.parent_ado_id is None


# ── Casos 11-12: que la consolidación ocurrió y que ADO no la pisa ───────────

def test_11_la_regex_vieja_del_migrador_se_borro_de_verdad():
    texto = (_BACKEND / "services" / "migrator_verify.py").read_text(encoding="utf-8")
    # SEMBRADO: un archivo vacío o mal leído también daría 0 ocurrencias.
    assert "_infer_type_from_labels" in texto, "el archivo no se leyó de verdad"
    assert texto.count("_TYPE_LABEL_RE") == 0, "quedó viva la regex propia del migrador"


def test_12_un_proyecto_ado_no_ejecuta_el_contrato_de_gitlab(bd, monkeypatch):
    """Backward-compat de ADO, byte-idéntico: el camino nuevo no corre ni una línea."""
    import api.tickets as t
    import services.gitlab_hierarchy as gh

    llamadas = []
    real = gh.clasificar_issue

    def _espia(body):
        llamadas.append(body)
        return real(body)

    monkeypatch.setattr(gh, "clasificar_issue", _espia)
    monkeypatch.setattr(t, "_provider_for_ticket", lambda **kw: None)
    monkeypatch.setattr(
        t, "resolve_project_context",
        lambda _p: SimpleNamespace(tracker_type="azure_devops", stacky_project_name="P",
                                   tracker_project="P"),
    )
    monkeypatch.setattr(t, "_ado_client_for_ticket", lambda **kw: object())
    monkeypatch.setattr(t, "sync_tickets", lambda **kw: {"fetched": 0, "created": 0,
                                                        "updated": 0, "removed": 0})
    t._sync_via_provider_or_ado("P")
    assert llamadas == [], f"un proyecto ADO ejecutó el contrato de GitLab: {llamadas}"

    # SEMBRADO: probar que el espía FUNCIONA. Un contador que nunca vio un positivo
    # da 0 también cuando el monkeypatch no tomó efecto (el import es local).
    _provider()._normalize_issue(_payload(1, labels=["type::bug"]))
    assert len(llamadas) == 1, "el espía no intercepta: el assert de arriba pasaba solo"


# ── Casos 13-14: la regresión que este plan crearía, y el camino de ADO ──────

def test_13_un_hijo_no_se_cuenta_como_epica_pero_la_epica_si_entra():
    """v2/C1 — LA REGRESIÓN QUE ESTE PLAN EVITA. `incident_context` matcheaba el
    substring "epic" a secas; con `epic::42` en los HIJOS, cada hijo pasaba a
    contar como épica y contaminaba el catálogo que ve el agente."""
    from services.incident_context import fetch_epic_catalog

    class _ProviderGitLab:
        # sin `fetch_epics`: fuerza la rama de labels (incident_context.py:237-240)
        def fetch_open_items(self, query):
            return [
                {"iid": 42, "title": "La épica", "state": "opened", "labels": ["type::epic"]},
                {"iid": 43, "title": "Un hijo", "state": "opened",
                 "labels": ["type::funcional", "epic::42"]},
            ]

    ids = [c["id"] for c in fetch_epic_catalog(_ProviderGitLab())]
    # El positivo va PRIMERO: sin él, `43 not in ids` pasa con el catálogo vacío.
    assert 42 in ids, f"la épica legítima dejó de entrar — el arreglo rompió el caso bueno: {ids}"
    assert 43 not in ids, f"un hijo (epic::42) se contó como épica: {ids}"


def test_14_el_camino_ado_de_fetch_epic_catalog_sigue_entrando():
    """El arreglo del substring no puede tocar la rama de `fields`
    (incident_context.py:235), que es por donde pasa ADO."""
    from services.incident_context import fetch_epic_catalog

    class _ProviderAdo:
        def fetch_open_items(self, query):
            return [
                {"id": 500, "fields": {"System.WorkItemType": "Epic",
                                       "System.Title": "Épica ADO", "System.State": "Active"}},
                {"id": 501, "fields": {"System.WorkItemType": "Task",
                                       "System.Title": "Tarea ADO", "System.State": "Active"}},
            ]

    catalogo = fetch_epic_catalog(_ProviderAdo())
    assert [c["id"] for c in catalogo] == [500], catalogo
    assert catalogo[0]["title"] == "Épica ADO"


# ── Caso 15: la extracción del upsert que F6 va a reusar ─────────────────────

def test_15_el_upsert_extraido_devuelve_created_noop_y_updated(bd, monkeypatch):
    """v2/C7 — los 3 valores de retorno EXISTEN (F6 depende de ellos) y la
    extracción no cambió el comportamiento: segunda corrida idéntica = "noop"."""
    import services.gitlab_sync as gs

    item = _provider()._normalize_issue(_payload(5, labels=["type::funcional", "epic::3"]))

    with gs.session_scope() as s:
        assert gs._upsert_ticket_gitlab(s, item, ctx=CTX, ahora=datetime.utcnow()) == "created"
    with gs.session_scope() as s:
        assert gs._upsert_ticket_gitlab(s, item, ctx=CTX, ahora=datetime.utcnow()) == "noop"

    cambiado = dict(item, title="otro título")
    with gs.session_scope() as s:
        assert gs._upsert_ticket_gitlab(s, cambiado, ctx=CTX, ahora=datetime.utcnow()) == "updated"

    from models import Ticket

    assert bd.session.query(Ticket).count() == 1, "el upsert duplicó la fila en vez de actualizarla"
