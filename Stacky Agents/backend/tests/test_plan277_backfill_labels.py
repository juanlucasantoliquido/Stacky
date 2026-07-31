"""tests/test_plan277_backfill_labels.py — Plan 277 F5.

QUÉ PRUEBA ESTE ARCHIVO, en una línea: que publicar la clasificación local como
etiquetas reales en el GitLab del operador NUNCA le borra nada, NUNCA escribe algo
que él no pidió ítem por ítem, y que ver el diff no escribe absolutamente nada.

LOS CUATRO CASOS QUE HACEN QUE EL ARCHIVO VALGA:
  · 1  — `planificar_backfill` hace CERO requests de escritura. Si el "plan" tocara
         GitLab, la palabra "plan" sería una mentira y el operador estaría aprobando
         algo que ya pasó.
  · 4  — con la flag apagada el endpoint responde 403 y NO se construye ni el
         proveedor. Es lo que hace que la flag sea un kill-switch real y no un cartel.
  · 6  — el cuerpo del PUT lleva `add_labels` y NADA más. La clave que manda el juego
         completo de etiquetas lo REEMPLAZA: borraría las que el operador puso a mano
         en su GitLab, sin aviso y sin vuelta atrás. Es destrucción de datos.
  · 8  — el 2º de 3 falla: se escribió 1, queda 1 pendiente y NO hay un tercer PUT ni
         un reintento del que falló. Escribir a ciegas después de un fallo contra el
         sistema de la empresa es exactamente lo que no se puede hacer.

AISLAMIENTO DE LA BD (desvío declarado, idéntico al de `test_plan277_clasificacion_
local.py`): `db.py` construye el engine AL IMPORTARSE y una sola vez por proceso, así
que la base es temporal POR MÓDULO (`tmp_path_factory`) y las tablas se limpian por
test. Que no se toque la base REAL del operador se verifica con un assert explícito
sobre la URL del engine. CERO red: el cliente HTTP es un doble que registra llamadas.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

FLAG = "STACKY_GITLAB_HIERARCHY_LABEL_WRITE_ENABLED"

CTX_GITLAB = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="ripley/agenda-web",
    tracker_type="gitlab",
)
CTX_ADO = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="Recovery",
    tracker_type="azure_devops",
)


# ── Infraestructura: BD temporal + dobles sin red ────────────────────────────


@pytest.fixture(scope="module")
def _bd_temporal(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("plan277f5") / "p277f5.db"
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{ruta.as_posix()}"
    os.environ["STACKY_SKIP_STARTUP_SYNC"] = "1"
    import db as db_mod

    url = str(db_mod.engine.url)
    assert "pytest" in url and url.endswith("p277f5.db"), (
        f"la BD del test NO está aislada de la del operador: {url}"
    )
    db_mod.init_db()
    return ruta


@pytest.fixture()
def client(_bd_temporal):
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _tabla_limpia(_bd_temporal):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        s.query(Ticket).delete()
    yield


@pytest.fixture()
def mod(monkeypatch):
    """El módulo bajo prueba, con el contexto de proyecto resuelto a GitLab."""
    import services.gitlab_hierarchy_backfill as m

    monkeypatch.setattr(m, "resolve_project_context", lambda *_a, **_k: CTX_GITLAB)
    return m


@pytest.fixture()
def flag_on(monkeypatch):
    import config

    monkeypatch.setattr(config.config, FLAG, True, raising=False)


class _ClienteFalso:
    """Doble del GitLabClient. Registra TODAS las llamadas y no toca la red.

    Emula `add_labels` como lo hace GitLab: AGREGA al juego que el issue ya tiene.
    Que el doble conserve las etiquetas previas es lo que permite que el caso 6
    distinga "agregó" de "reemplazó" mirando el estado final, y no solo el cuerpo.
    """

    def __init__(self, issues: dict, *, fallar=None):
        self.issues = {int(k): dict(v) for k, v in issues.items()}
        self.llamadas: list[tuple] = []
        self.fallar = {int(x) for x in (fallar or ())}

    def _project_path(self) -> str:
        return "ripley%2Fagenda-web"

    def _request(self, metodo, ruta, *, params=None, json_body=None, files=None):
        self.llamadas.append((metodo, ruta, json_body))
        iid = int(str(ruta).rsplit("/", 1)[-1])
        if metodo == "GET":
            if iid not in self.issues:
                from services.tracker_provider import TrackerApiError

                raise TrackerApiError(404, f"issue {iid} inexistente", kind="not_found")
            return dict(self.issues[iid]), {}
        if metodo == "PUT":
            if iid in self.fallar:
                from services.tracker_provider import TrackerApiError

                raise TrackerApiError(500, f"GitLab falló en el issue {iid}", kind="server")
            crudas = (json_body or {}).get("add_labels") or ""
            actuales = list(self.issues[iid].get("labels") or [])
            for etiqueta in [e for e in str(crudas).split(",") if e]:
                if etiqueta not in actuales:
                    actuales.append(etiqueta)
            self.issues[iid]["labels"] = actuales
            return dict(self.issues[iid]), {}
        raise AssertionError(f"método HTTP inesperado en el doble: {metodo}")

    @property
    def escrituras(self) -> list[tuple]:
        return [c for c in self.llamadas if c[0] in ("PUT", "POST")]

    @property
    def puts(self) -> list[tuple]:
        return [c for c in self.llamadas if c[0] == "PUT"]


def _proveedor(cliente):
    """El proveedor REAL con un cliente falso adentro.

    A propósito no es un doble del proveedor: así `get_item` y `_normalize_issue`
    —o sea, el contrato de tipo y padre— corren de verdad. Un doble del proveedor
    tendría que reimplementar la normalización, que es justo el motor nº 5 que este
    plan existe para no crear.
    """
    from services.gitlab_provider import GitLabTrackerProvider

    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    p._client = cliente
    p._project = "ripley/agenda-web"
    p._group = ""
    p._epics_native = False
    return p


def _issue(iid: int, *, labels=None, title=None) -> dict:
    return {
        "id": 1000 + iid,
        "iid": iid,
        "title": title or f"issue {iid}",
        "description": "",
        "state": "opened",
        "labels": list(labels or []),
        "web_url": f"https://gitlab.empresa/ripley/agenda-web/-/issues/{iid}",
        "updated_at": "2026-07-31T10:00:00Z",
    }


def _sembrar(filas) -> list[int]:
    from db import session_scope
    from models import Ticket

    ids = []
    with session_scope() as session:
        for f in filas:
            t = Ticket(**f)
            session.add(t)
            session.flush()
            ids.append(t.id)
    return ids


def _fila(ado_id, *, local_tipo=None, local_padre=None, stacky="RIPLEY", tracker="gitlab"):
    return {
        "ado_id": ado_id,
        "external_id": 1000 + ado_id,
        "project": "ripley/agenda-web",
        "stacky_project_name": stacky,
        "tracker_type": tracker,
        "title": f"issue {ado_id}",
        "ado_state": "opened",
        "work_item_type": "Issue",
        "ado_url": f"https://gitlab.empresa/ripley/agenda-web/-/issues/{ado_id}",
        "local_work_item_type": local_tipo,
        "local_parent_iid": local_padre,
    }


def _explota(*_a, **_k):
    raise AssertionError(
        "no se puede construir el proveedor de GitLab en este camino: sería un request "
        "contra el sistema del operador"
    )


# ── Caso 1 ───────────────────────────────────────────────────────────────────


def test_caso_1_planificar_no_hace_ninguna_escritura(mod):
    """El 'plan' es de verdad read-only: 0 PUT y 0 POST. Los GET sí."""
    _sembrar([_fila(10, local_tipo="Epic"), _fila(11, local_padre=10)])
    cliente = _ClienteFalso({10: _issue(10), 11: _issue(11)})

    plan = mod.planificar_backfill("RIPLEY", provider=_proveedor(cliente))

    assert plan["total"] == 2
    assert cliente.escrituras == [], f"el plan escribió en GitLab: {cliente.escrituras}"
    assert [c[0] for c in cliente.llamadas] == ["GET", "GET"]


# ── Caso 2 ───────────────────────────────────────────────────────────────────


def test_caso_2_plan_lista_la_etiqueta_de_tipo_a_agregar(mod):
    """Camino feliz: local 'Epic', sin etiqueta remota ⇒ agregar=['type::epic']."""
    _sembrar([_fila(10, local_tipo="Epic")])
    cliente = _ClienteFalso({10: _issue(10, title="Violeta Lugo")})

    plan = mod.planificar_backfill("RIPLEY", provider=_proveedor(cliente))

    assert plan["total"] == 1 and plan["con_conflicto"] == 0
    cambio = plan["cambios"][0]
    assert cambio["agregar"] == ["type::epic"]
    assert cambio["ya_tiene"] == []
    assert cambio["conflicto"] is False
    # El diff se le muestra al operador: tiene que poder identificar el issue.
    assert cambio["ado_id"] == 10 and cambio["iid"] == 10
    assert cambio["title"] == "Violeta Lugo"
    assert cambio["url"].endswith("/issues/10")


# ── Caso 3 ───────────────────────────────────────────────────────────────────


def test_caso_3_tipo_remoto_distinto_es_conflicto_y_no_se_agrega(mod):
    """§3.2: GitLab manda. Se lista para que el operador lo vea, no se toca."""
    _sembrar([_fila(11, local_tipo="Epic"), _fila(10, local_tipo="Epic")])
    cliente = _ClienteFalso(
        {11: _issue(11, labels=["type::bug"]), 10: _issue(10)}
    )

    plan = mod.planificar_backfill("RIPLEY", provider=_proveedor(cliente))
    por_id = {c["ado_id"]: c for c in plan["cambios"]}

    # POSITIVO SEMBRADO: el otro ticket, con la MISMA clasificación local, sí agrega.
    assert por_id[10]["agregar"] == ["type::epic"] and por_id[10]["conflicto"] is False

    assert por_id[11]["conflicto"] is True
    assert por_id[11]["agregar"] == []
    assert por_id[11]["ya_tiene"] == ["type::bug"]
    assert plan["con_conflicto"] == 1


# ── Caso 4 ───────────────────────────────────────────────────────────────────


def test_caso_4_flag_apagada_devuelve_403_y_cero_requests(client, monkeypatch):
    """La flag es un kill-switch real: 403 y ni siquiera se construye el proveedor."""
    import config
    import services.gitlab_hierarchy_backfill as m

    _sembrar([_fila(10, local_tipo="Epic")])
    monkeypatch.setattr(config.config, FLAG, False, raising=False)
    # Si el endpoint dejara pasar, esto revienta y el 403 no llega: el gate no puede
    # ser "la UI no muestra el botón".
    monkeypatch.setattr(m, "_proveedor", _explota)

    resp = client.post(
        "/api/tickets/hierarchy/backfill/apply",
        json={"project": "RIPLEY", "ado_ids": [10]},
    )

    assert resp.status_code == 403
    cuerpo = resp.get_json()
    assert cuerpo["ok"] is False and cuerpo["error"] == "flag_off"
    # Nombra la flag Y dónde encenderla: un 403 mudo manda al operador a leer código.
    assert cuerpo["flag"] == FLAG
    assert FLAG in cuerpo["message"] and "flags" in cuerpo["message"].lower()


# ── Caso 5 ───────────────────────────────────────────────────────────────────


def test_caso_5_lista_vacia_no_escribe_nada(mod, flag_on):
    """'Nunca todos por defecto': sin ids explícitos no se toca un solo issue."""
    _sembrar([_fila(10, local_tipo="Epic"), _fila(11, local_tipo="Epic")])
    cliente = _ClienteFalso({10: _issue(10), 11: _issue(11)})

    r = mod.ejecutar_backfill("RIPLEY", [], provider=_proveedor(cliente))

    assert r["escritos"] == 0
    assert r["fallidos"] == [] and r["pendientes"] == []
    # Cero requests de CUALQUIER tipo: con la lista vacía ni se lee el estado remoto.
    assert cliente.llamadas == []


# ── Caso 6 ───────────────────────────────────────────────────────────────────


def test_caso_6_el_put_usa_add_labels_y_nada_mas(mod, flag_on):
    """La clave que reemplaza el juego entero borraría las etiquetas del operador."""
    _sembrar([_fila(12, local_tipo="Epic", local_padre=10)])
    # El issue YA tiene etiquetas del operador que nada tiene por qué tocar.
    cliente = _ClienteFalso({12: _issue(12, labels=["prioridad::alta", "equipo::pagos"])})

    r = mod.ejecutar_backfill("RIPLEY", [12], provider=_proveedor(cliente))

    assert r["escritos"] == 1
    assert len(cliente.puts) == 1
    _metodo, _ruta, cuerpo = cliente.puts[0]
    # El cuerpo tiene UNA sola clave y es la aditiva.
    assert set(cuerpo) == {"add_labels"}
    assert cuerpo["add_labels"] == "type::epic,epic::10"
    # Y el efecto: las etiquetas previas del operador SIGUEN ahí.
    assert cliente.issues[12]["labels"] == [
        "prioridad::alta", "equipo::pagos", "type::epic", "epic::10",
    ]


# ── Caso 7 ───────────────────────────────────────────────────────────────────


def test_caso_7_el_conflicto_se_rechaza_aunque_venga_en_la_lista(mod, flag_on):
    """El rechazo vive en el servidor, no solo en la pantalla."""
    _sembrar([_fila(11, local_tipo="Epic"), _fila(10, local_tipo="Epic")])
    cliente = _ClienteFalso({11: _issue(11, labels=["type::bug"]), 10: _issue(10)})

    r = mod.ejecutar_backfill("RIPLEY", [11, 10], provider=_proveedor(cliente))

    # POSITIVO SEMBRADO: el 10 sí se escribió, así el "no se escribió" del 11 no
    # puede venir de que la función no escriba nunca.
    assert r["escritos"] == 1
    assert r["omitidos"] == 1
    assert [int(str(c[1]).rsplit("/", 1)[-1]) for c in cliente.puts] == [10]
    assert cliente.issues[11]["labels"] == ["type::bug"]


# ── Caso 8 ───────────────────────────────────────────────────────────────────


def test_caso_8_corta_ante_el_primer_fallo_sin_reintentar(mod, flag_on):
    """Corte duro: 1 escrito, 1 fallido, 1 pendiente y NINGÚN request de más."""
    _sembrar([
        _fila(20, local_tipo="Epic"),
        _fila(21, local_tipo="Epic"),
        _fila(22, local_tipo="Epic"),
    ])
    cliente = _ClienteFalso(
        {20: _issue(20), 21: _issue(21), 22: _issue(22)}, fallar={21},
    )

    r = mod.ejecutar_backfill("RIPLEY", [20, 21, 22], provider=_proveedor(cliente))

    assert r["escritos"] == 1
    assert [f["ado_id"] for f in r["fallidos"]] == [21]
    assert "21" in r["fallidos"][0]["error"]
    assert r["pendientes"] == [22]
    # DOS PUT exactos: el que salió bien y el que falló. No hay tercero (el pendiente)
    # ni un segundo intento del 21.
    assert [int(str(c[1]).rsplit("/", 1)[-1]) for c in cliente.puts] == [20, 21]
    assert cliente.issues[22]["labels"] == []


# ── Caso 9 ───────────────────────────────────────────────────────────────────


def test_caso_9_un_id_de_otro_proyecto_no_se_escribe(mod, flag_on):
    """Cross-project: nunca se escribe en el proyecto equivocado."""
    _sembrar([_fila(10, local_tipo="Epic"), _fila(99, local_tipo="Epic", stacky="OTRO")])
    cliente = _ClienteFalso({10: _issue(10), 99: _issue(99)})

    r = mod.ejecutar_backfill("RIPLEY", [99, 10], provider=_proveedor(cliente))

    assert r["escritos"] == 1 and r["omitidos"] == 1
    assert [int(str(c[1]).rsplit("/", 1)[-1]) for c in cliente.puts] == [10]
    assert cliente.issues[99]["labels"] == []


# ── Caso 10 ──────────────────────────────────────────────────────────────────


def test_caso_10_dos_corridas_seguidas_son_idempotentes(mod, flag_on):
    """La 2ª no rompe y no duplica: la etiqueta ya está, no hay nada que agregar."""
    _sembrar([_fila(10, local_tipo="Epic")])
    cliente = _ClienteFalso({10: _issue(10)})
    prov = _proveedor(cliente)

    r1 = mod.ejecutar_backfill("RIPLEY", [10], provider=prov)
    etiquetas_tras_1 = list(cliente.issues[10]["labels"])
    r2 = mod.ejecutar_backfill("RIPLEY", [10], provider=prov)

    assert r1["escritos"] == 1
    assert etiquetas_tras_1 == ["type::epic"]
    # La 2ª corrida ve que ya la tiene: no hay nada que agregar y no se emite el PUT.
    assert r2["escritos"] == 0 and r2["omitidos"] == 1
    assert r2["fallidos"] == []
    assert len(cliente.puts) == 1
    assert cliente.issues[10]["labels"] == ["type::epic"]


# ── Caso 11 ──────────────────────────────────────────────────────────────────


def test_caso_11_proyecto_ado_no_construye_cliente_de_gitlab(monkeypatch):
    """Backward-compat: en un proyecto ADO el plan es vacío y no se toca GitLab."""
    import services.gitlab_client as gc
    import services.gitlab_hierarchy_backfill as m

    _sembrar([_fila(10, local_tipo="Epic")])

    def _no_construir(*_a, **_k):
        raise AssertionError("se construyó un GitLabClient en un proyecto que no es GitLab")

    monkeypatch.setattr(gc.GitLabClient, "__init__", _no_construir)
    monkeypatch.setattr(m, "_proveedor", _explota)

    monkeypatch.setattr(m, "resolve_project_context", lambda *_a, **_k: CTX_ADO)
    plan = mod_plan = m.planificar_backfill("RIPLEY")
    assert plan["total"] == 0 and plan["cambios"] == [] and plan["con_conflicto"] == 0

    # POSITIVO SEMBRADO: la MISMA fila, con el mismo sembrado, da total=1 cuando el
    # proyecto sí es GitLab. Sin esto, el 0 podría venir de que la tabla está vacía.
    monkeypatch.setattr(m, "resolve_project_context", lambda *_a, **_k: CTX_GITLAB)
    cliente = _ClienteFalso({10: _issue(10)})
    monkeypatch.setattr(m, "_proveedor", lambda *_a, **_k: _proveedor(cliente))
    assert m.planificar_backfill("RIPLEY")["total"] == 1
    assert mod_plan["proyecto"] == "RIPLEY"
