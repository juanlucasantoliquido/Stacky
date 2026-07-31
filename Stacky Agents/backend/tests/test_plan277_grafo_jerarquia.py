"""tests/test_plan277_grafo_jerarquia.py — Plan 277 F6.

Los TRES modos de falla del grafo, cada gate corrido CONTRA el defecto:

1. **El índice colisiona.** `ado_id_to_ticket[t.ado_id]` indexaba por `ado_id` a
   secas sobre una bolsa donde conviven ADO y GitLab (`_ticket_project_filter` NO
   filtra por tracker). Con una colisión, el 2º ticket PISA al 1º y en el loop de
   armado los dos resuelven al MISMO nodo: uno sale duplicado y el otro desaparece.
   Lo que detecta eso es el CONTEO DE APARICIONES del caso 10, no el "no cuelga del
   padre equivocado" (que pasa igual con el índice roto).
2. **La auto-referencia se lleva el ticket puesto.** `d["children"].append(d)` deja
   al nodo colgado de sí mismo. MEDIDO contra el algoritmo original: sin la colisión
   de índice el nodo no es alcanzable desde `epics`/`orphans`, así que `jsonify` ni
   lo visita — no hay 500, el ticket DESAPARECE en silencio (un ciclo A↔B se lleva a
   los dos). El 500 "Circular reference detected" aparece cuando además colisiona el
   índice, porque ahí el MISMO dict está en `epics` y se contiene a sí mismo. Por eso
   el caso 1 exige que el ticket esté en `orphans` (el daño real) Y serializa la
   respuesta: un `assert status == 200` solo no prueba ninguna de las dos cosas.
3. **Los padres cerrados no vienen.** El sync pide `state="open"`, así que una épica
   cerrada nunca llega y sus hijos quedan sueltos. El caso 5 siembra primero la
   corrida con la flag OFF que los deja huérfanos: un test de "ahora sí cuelga" que
   nunca vio el "antes" no prueba nada.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CTX = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="ripley/agenda-web",
    tracker_type="gitlab",
)


@pytest.fixture(scope="module")
def _bd_temporal(tmp_path_factory):
    """UNA base para todo el archivo, a propósito.

    `db.py` construye el engine al IMPORTARSE y una sola vez por proceso, así que
    una BD por test es imposible: el engine se quedaría apuntando a la del primer
    test. El aislamiento que importa es respecto de la BD REAL del operador (181 MB)
    y eso se verifica abajo. Las tablas se limpian por test en `_sembrar`.
    """
    ruta = tmp_path_factory.mktemp("plan277g") / "p277g.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{ruta.as_posix()}"
    os.environ["STACKY_SKIP_STARTUP_SYNC"] = "1"
    import db as db_mod

    url = str(db_mod.engine.url)
    assert "pytest" in url and url.endswith("p277g.db"), (
        f"la BD del test NO está aislada de la del operador: {url}"
    )
    return ruta


@pytest.fixture()
def client(_bd_temporal):
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _sembrar(filas):
    from db import session_scope
    from models import Ticket

    with session_scope() as session:
        session.query(Ticket).delete()
        for f in filas:
            session.add(Ticket(**f))


def _limpiar():
    _sembrar([])


def _fila(ado_id, external_id, *, tipo="Issue", parent=None, tracker="gitlab",
          stacky="RIPLEY", proyecto="ripley/agenda-web"):
    return {
        "ado_id": ado_id, "external_id": external_id, "project": proyecto,
        "stacky_project_name": stacky, "tracker_type": tracker,
        "title": f"issue {ado_id}", "ado_state": "opened",
        "work_item_type": tipo, "parent_ado_id": parent,
    }


def _hierarchy(client, monkeypatch, project="RIPLEY"):
    import api.tickets as t

    monkeypatch.setattr(t, "resolve_project_context", lambda **kw: CTX)
    resp = client.get(f"/api/tickets/hierarchy?project={project}")
    return resp, resp.get_json()


def _todos(body) -> list[dict]:
    """Todos los nodos del grafo, bajando por `children`."""
    salida: list[dict] = []

    def _rec(nodo):
        salida.append(nodo)
        for hijo in nodo.get("children") or []:
            _rec(hijo)

    for raiz in body["epics"] + body["orphans"]:
        _rec(raiz)
    return salida


def _por_clave(nodos) -> dict:
    """Cuenta apariciones por `(tracker_type, ado_id)` — la clave real del grafo."""
    cuenta: dict = {}
    for n in nodos:
        k = (n.get("tracker_type"), n.get("ado_id"))
        cuenta[k] = cuenta.get(k, 0) + 1
    return cuenta


# ── Casos 1-4, 10-12: el endpoint del grafo ─────────────────────────────────

def test_01_auto_padre_da_200_y_la_respuesta_es_serializable(client, monkeypatch):
    """`parent_ado_id == ado_id` hacía `d["children"].append(d)`. MEDIDO: el ticket
    se volvía inalcanzable desde `epics`/`orphans` y desaparecía de la respuesta sin
    un solo error (y con el índice colisionado, el mismo dict en `epics` daba el 500
    de "Circular reference detected"). El gate corre contra las dos formas."""
    _sembrar([_fila(7, 1007, parent=7)])

    resp, body = _hierarchy(client, monkeypatch)

    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    assert [n["ado_id"] for n in body["orphans"]] == [7], body
    # Un `assert status == 200` solo no prueba que la estructura sea serializable
    # río abajo: acá se serializa de verdad.
    json.dumps(body)
    suelto = body["orphans"][0]
    assert suelto["children"] == [], "el ticket quedó como hijo de sí mismo"


def test_02_ciclo_indirecto_deja_a_los_dos_sueltos_y_avisa(client, monkeypatch):
    """A→B→A. Ninguno de los dos puede colgar del otro sin cerrar el ciclo."""
    import api.tickets as t

    _sembrar([_fila(1, 1001, parent=2), _fila(2, 1002, parent=1)])

    avisos = []
    monkeypatch.setattr(t.logger, "warning", lambda *a, **k: avisos.append(a))

    resp, body = _hierarchy(client, monkeypatch)

    assert resp.status_code == 200
    assert sorted(n["ado_id"] for n in body["orphans"]) == [1, 2], body
    assert body["epics"] == []
    assert avisos, "el enlace se descartó en silencio: el operador no puede saberlo"


def test_03_cadena_de_60_no_revienta_ni_pierde_tickets(client, monkeypatch):
    """El tope de 50 saltos. Con 60 encadenados el recorrido tiene que cortar solo,
    devolver 200 y NO perder ningún ticket por el camino."""
    filas = [_fila(1, 1001, tipo="Epic")]
    filas += [_fila(i, 1000 + i, parent=i - 1) for i in range(2, 61)]
    _sembrar(filas)

    resp, body = _hierarchy(client, monkeypatch)

    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    json.dumps(body)
    nodos = _todos(body)
    assert len(nodos) == 60, f"se perdieron o duplicaron tickets: {len(nodos)}"
    assert len(body["epics"]) == 1


def test_04_epica_con_las_tres_fases_del_contrato(client, monkeypatch):
    """El caso 'Violeta Lugo' completo: una épica y sus tres fases colgando."""
    _sembrar([
        _fila(1, 1001, tipo="Epic"),
        _fila(2, 1002, tipo="Funcional", parent=1),
        _fila(3, 1003, tipo="Tecnico", parent=1),
        _fila(4, 1004, tipo="Implementacion", parent=1),
    ])

    resp, body = _hierarchy(client, monkeypatch)

    assert resp.status_code == 200
    assert len(body["epics"]) == 1, body
    hijos = body["epics"][0]["children"]
    assert len(hijos) == 3, hijos
    assert sorted(h["work_item_type"] for h in hijos) == [
        "Funcional", "Implementacion", "Tecnico",
    ]
    assert body["orphans"] == [], body["orphans"]


def test_10_colision_de_ado_id_entre_trackers_no_duplica_ni_pierde(client, monkeypatch):
    """v2/C8 — EL GATE DEL ÍNDICE. Con `ado_id` pelado, los dos tickets de ado_id=1
    resuelven al MISMO nodo: uno sale DOS veces y el otro DESAPARECE. El conteo de
    apariciones es lo único que lo detecta; 'no cuelga del padre equivocado' pasa
    igual con el índice roto."""
    _sembrar([
        _fila(1, 5001, tipo="Epic", tracker="azure_devops"),   # épica de ADO
        _fila(1, 1001, tracker="gitlab"),                      # MISMO ado_id, otro tracker
        _fila(2, 1002, parent=1, tracker="gitlab"),            # hijo de GitLab
    ])

    resp, body = _hierarchy(client, monkeypatch)
    assert resp.status_code == 200
    nodos = _todos(body)
    cuenta = _por_clave(nodos)

    assert cuenta.get(("azure_devops", 1)) == 1, f"la épica de ADO se perdió/duplicó: {cuenta}"
    assert cuenta.get(("gitlab", 1)) == 1, f"el ticket de GitLab se perdió/duplicó: {cuenta}"
    assert cuenta.get(("gitlab", 2)) == 1, f"el hijo se perdió/duplicó: {cuenta}"

    epica_ado = [n for n in nodos if n["tracker_type"] == "azure_devops"][0]
    assert epica_ado["children"] == [], (
        "el hijo de GitLab colgó de la épica de ADO: los ids son namespaces distintos"
    )
    padre_gl = [n for n in nodos if (n["tracker_type"], n["ado_id"]) == ("gitlab", 1)][0]
    assert [h["ado_id"] for h in padre_gl["children"]] == [2]


def test_11_cada_causa_de_orfandad_tiene_su_propio_motivo(client, monkeypatch):
    """Un motivo que devuelve siempre lo mismo es peor que no tenerlo."""
    _sembrar([
        _fila(10, 1010),                                    # sin padre declarado
        _fila(20, 1020, parent=20),                         # auto padre
        _fila(30, 1030, parent=40),                         # ciclo 30 <-> 40
        _fila(40, 1040, parent=30),
        _fila(50, 1050, parent=999),                        # el padre no existe
        _fila(60, 1060, parent=70),                         # el 70 existe, pero en ADO
        _fila(70, 5070, tracker="azure_devops"),
    ])

    resp, body = _hierarchy(client, monkeypatch)
    assert resp.status_code == 200
    motivos = {n["ado_id"]: n.get("motivo_huerfano") for n in body["orphans"]}

    esperado = {
        10: "sin_padre_declarado",
        20: "auto_padre",
        30: "ciclo",
        50: "padre_ausente_en_bd",
        60: "padre_de_otro_tracker",
    }
    assert {k: motivos.get(k) for k in esperado} == esperado, motivos
    assert len(set(esperado.values())) == 5, "dos causas comparten el mismo motivo"


def test_12_un_ticket_que_si_cuelga_no_trae_el_motivo(client, monkeypatch):
    """El motivo es del huérfano, no ruido en todos lados."""
    _sembrar([_fila(1, 1001, tipo="Epic"), _fila(2, 1002, parent=1)])

    resp, body = _hierarchy(client, monkeypatch)

    assert resp.status_code == 200
    hijo = body["epics"][0]["children"][0]
    assert hijo["ado_id"] == 2
    assert "motivo_huerfano" not in hijo, hijo
    assert "motivo_huerfano" not in body["epics"][0]


# ── Casos 5-9: el sync que trae los padres que faltan ────────────────────────

def _issue(iid, id_=None, *, tipo="Issue", parent=None, estado="opened"):
    """El shape que emite `_normalize_issue` (el mismo que devuelve `get_item`)."""
    return {
        "id": str(id_ if id_ is not None else 1000 + int(iid)),
        "iid": str(iid),
        "title": f"issue {iid}",
        "description": "d",
        "state": estado,
        "labels": [],
        "assignees": [],
        "web_url": f"https://gl.interno/ripley/agenda-web/-/issues/{iid}",
        "updated_at": "2026-07-31T00:00:00Z",
        "work_item_type": tipo,
        "parent": parent,
        "origen_tipo": "label" if tipo != "Issue" else "defecto",
        "origen_padre": "label" if parent else "ninguno",
    }


class _ProviderFalso:
    name = "gitlab"

    def __init__(self, items, *, padres=None, revienta=()):
        self._items = items
        self._padres = padres or {}
        self._revienta = set(revienta)
        self.pedidos: list[str] = []

    def fetch_open_items(self, query):
        return list(self._items)

    def get_item(self, item_id: str) -> dict:
        self.pedidos.append(item_id)
        if int(item_id) in self._revienta:
            raise RuntimeError(f"404 en el iid {item_id}")
        return self._padres[int(item_id)]


def _sync(monkeypatch, provider, ctx=CTX):
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "resolve_project_context", lambda _p: ctx)
    return gs.sync_gitlab_tickets("RIPLEY", provider=provider)


def test_05_el_padre_cerrado_ausente_se_trae_y_los_hijos_dejan_de_ser_sueltos(
    client, monkeypatch
):
    """SEMBRADO PRIMERO CON LA FLAG APAGADA. Un test de 'ahora sí cuelga' que nunca
    vio el 'antes' no prueba nada: podría estar colgando por otro motivo."""
    import config as cmod

    _limpiar()
    epica_cerrada = _issue(1, 1001, tipo="Epic", estado="closed")
    provider = _ProviderFalso([_issue(2, 1002, parent=1)], padres={1: epica_cerrada})

    # ── ANTES: sin la flag, la épica cerrada no llega y el hijo queda suelto ──
    monkeypatch.setattr(cmod.config, "STACKY_GITLAB_SYNC_PARENTS_ENABLED", False,
                        raising=False)
    antes = _sync(monkeypatch, provider)
    assert antes["padres_traidos"] == 0 and provider.pedidos == []
    _, body_antes = _hierarchy(client, monkeypatch)
    assert body_antes["epics"] == [], body_antes
    assert [n["ado_id"] for n in body_antes["orphans"]] == [2], body_antes
    assert body_antes["orphans"][0]["motivo_huerfano"] == "padre_ausente_en_bd"

    # ── DESPUÉS: con la flag, se pide ese iid y el hijo cuelga ────────────────
    monkeypatch.setattr(cmod.config, "STACKY_GITLAB_SYNC_PARENTS_ENABLED", True,
                        raising=False)
    despues = _sync(monkeypatch, provider)
    assert despues["padres_traidos"] == 1, despues
    assert provider.pedidos == ["1"], provider.pedidos

    _, body = _hierarchy(client, monkeypatch)
    assert len(body["epics"]) == 1, body
    assert body["epics"][0]["ado_state"] == "closed"
    assert [h["ado_id"] for h in body["epics"][0]["children"]] == [2], body["epics"][0]
    assert body["orphans"] == [], body["orphans"]

    # ── Y NO SE PIDE DE NUEVO. Una vez que el padre está en la base entra en
    # `presentes`, así que la 3ª corrida no vuelve a golpear el GitLab del operador
    # ni marca al padre como desaparecido (no vino en el listado de abiertos).
    tercera = _sync(monkeypatch, provider)
    assert tercera["padres_traidos"] == 0, tercera
    assert provider.pedidos == ["1"], f"se re-pidió un padre que ya estaba: {provider.pedidos}"
    assert tercera["removed"] == 0, f"el padre cerrado se contó como desaparecido: {tercera}"
    _, body3 = _hierarchy(client, monkeypatch)
    assert [h["ado_id"] for h in body3["epics"][0]["children"]] == [2], body3


def test_06_con_la_flag_apagada_no_se_pide_un_solo_padre(client, monkeypatch):
    """Kill-switch REAL, no una flag registrada pero muerta. El gate corre contra el
    defecto: HAY un padre faltante para pedir."""
    import config as cmod

    _limpiar()
    provider = _ProviderFalso([_issue(2, 1002, parent=1)],
                              padres={1: _issue(1, 1001, tipo="Epic", estado="closed")})
    monkeypatch.setattr(cmod.config, "STACKY_GITLAB_SYNC_PARENTS_ENABLED", False,
                        raising=False)

    res = _sync(monkeypatch, provider)

    assert provider.pedidos == [], provider.pedidos
    assert res["padres_traidos"] == 0
    assert res["padres_omitidos_por_tope"] == 0


def test_07_sesenta_padres_faltantes_se_recortan_a_50_y_se_avisa(client, monkeypatch):
    """La cota que NO miente: una cota silenciosa se lee como 'trajimos todos'."""
    import services.gitlab_sync as gs

    _limpiar()
    hijos = [_issue(i, 1000 + i, parent=100 + i) for i in range(1, 61)]
    padres = {100 + i: _issue(100 + i, 2000 + i, tipo="Epic", estado="closed")
              for i in range(1, 61)}
    provider = _ProviderFalso(hijos, padres=padres)

    avisos = []
    monkeypatch.setattr(gs.logger, "warning",
                        lambda msg, *a, **k: avisos.append(msg % a if a else msg))

    res = _sync(monkeypatch, provider)

    assert res["padres_traidos"] == 50, res
    assert res["padres_omitidos_por_tope"] == 10, res
    assert len(provider.pedidos) == 50, len(provider.pedidos)
    recorte = [m for m in avisos if "tope" in m]
    assert recorte, f"el tope recortó en silencio: {avisos}"
    assert "60" in recorte[0] and "50" in recorte[0] and "10" in recorte[0], recorte[0]


def test_08_un_padre_roto_no_tumba_la_corrida(client, monkeypatch):
    """Un 404 en UN padre no puede costar el resto del sync."""
    _limpiar()
    padres = {
        1: _issue(1, 1001, tipo="Epic", estado="closed"),
        3: _issue(3, 1003, tipo="Epic", estado="closed"),
    }
    provider = _ProviderFalso(
        [_issue(10, 1010, parent=1), _issue(11, 1011, parent=3)],
        padres=padres, revienta=(1,),
    )

    res = _sync(monkeypatch, provider)

    assert res["padres_fallidos"] == 1, res
    assert res["padres_traidos"] == 1, res
    assert res["created"] == 2, "la corrida se cayó y perdió los issues del listado"

    _, body = _hierarchy(client, monkeypatch)
    assert [e["ado_id"] for e in body["epics"]] == [3], body
    assert [n["ado_id"] for n in body["orphans"]] == [10], body


def test_09_un_proyecto_ado_no_pide_ni_un_padre(client, monkeypatch):
    """Backward-compat: para azure_devops el bloque de padres no ejecuta ni una
    línea, porque el sync de GitLab ni siquiera se resuelve."""
    import api.tickets as t

    provider = _ProviderFalso([], padres={})
    resueltos = []
    monkeypatch.setattr(t, "_provider_for_ticket", lambda **kw: None)
    monkeypatch.setattr(
        t, "resolve_project_context",
        lambda _p: SimpleNamespace(tracker_type="azure_devops", stacky_project_name="P",
                                   tracker_project="P"),
    )

    def _fabrica(_p):
        resueltos.append(_p)
        return provider

    monkeypatch.setattr(t, "get_tracker_provider", _fabrica)
    monkeypatch.setattr(t, "_ado_client_for_ticket", lambda **kw: object())
    monkeypatch.setattr(t, "sync_tickets", lambda **kw: {"fetched": 0, "created": 0,
                                                        "updated": 0, "removed": 0})

    t._sync_via_provider_or_ado("P")

    assert resueltos == [], "para un proyecto ADO se resolvió un provider de GitLab"
    assert provider.pedidos == [], "un proyecto ADO salió a pedir padres a GitLab"
