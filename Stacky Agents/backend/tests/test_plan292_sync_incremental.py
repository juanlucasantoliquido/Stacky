"""tests/test_plan292_sync_incremental.py — Plan 292 F1 + F5.

El sync de GitLab deja de preguntar todo cada vez. Este archivo es el gate de
CORRECTITUD del plan, y tiene DOS invariantes centrales, no uno:

- LECTURA: en modo parcial la regla de ausencia (gitlab_sync.py:310-326) se apaga
  POR COMPLETO. El caso central usa un delta PARCIAL NO VACIO a proposito: con la
  tanda VACIA el `if vistos_external:` preexistente ya corta, los asserts pasan
  SIN el plan, y la mitad de contraste no puede fallar. Medido contra el codigo
  de hoy: con un delta de 1 sobre 3 filas, `removed=2`.
- ESCRITURA: en modo parcial la query es `state="all"`, asi que llegan CERRADOS.
  Un cerrado que no tiene fila local NO puede crear una. Medido contra el codigo
  de hoy: `created=1`, la fila (77,'closed') creada de la nada. Nadie la borraria
  nunca (el modo COMPLETO marca por ausencia, jamas borra), `list_tickets` no
  filtra por estado y ordena por last_synced_at DESC con tope 500 ⇒ la fila
  fantasma va ARRIBA del tablero y desaloja abiertos reales.
"""
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ───────────────────────── F1 — el carril ─────────────────────────


def test_trackerquery_acepta_updated_after_y_su_default_es_none():
    from services.tracker_provider import TrackerQuery

    assert TrackerQuery().updated_after is None
    q = TrackerQuery(updated_after="2026-01-01T00:00:00Z")
    assert q.updated_after == "2026-01-01T00:00:00Z"


def _params(query):
    from services.gitlab_provider import GitLabTrackerProvider

    # `_query_to_gitlab_params` no toca `self`: se invoca sin construir el
    # proveedor, que exigiria configuracion del operador.
    return GitLabTrackerProvider._query_to_gitlab_params(None, query)


def test_query_sin_updated_after_no_emite_el_parametro():
    from services.tracker_provider import TrackerQuery

    params = _params(TrackerQuery(state="open"))
    assert params == {"state": "opened"}
    assert "updated_after" not in params


def test_query_con_updated_after_lo_emite_tal_cual():
    from services.tracker_provider import TrackerQuery

    params = _params(TrackerQuery(state="all", updated_after="2026-08-01T10:00:00Z"))
    assert params["updated_after"] == "2026-08-01T10:00:00Z"
    # `state="all"` NO emite el parametro `state`: GitLab sin `state` devuelve
    # todos, que es exactamente lo que el modo parcial necesita.
    assert "state" not in params


# ───────────────────────── F5 — infraestructura ─────────────────────────


@pytest.fixture()
def bd(tmp_path, monkeypatch):
    """BD sqlite temporal, aislada de la del operador. Molde de
    tests/test_plan276_gitlab_sync.py:24-95."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'plan292.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")

    from db import Base
    import models  # noqa: F401  — su import registra las tablas en Base.metadata

    ruta = (tmp_path / "plan292.db").as_posix()
    motor = create_engine(f"sqlite:///{ruta}", future=True)
    Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(motor)
    assert tmp_path.name in str(motor.url), f"la BD del test NO esta aislada: {motor.url}"

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

    # `services.gitlab_sync` importo `session_scope` POR VALOR: parchear
    # `db.session_scope` no tendria efecto y el sync escribiria en la BD real.
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "session_scope", _scope_de_test)

    class _BD:
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


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """R8 — la marca va a un temporal, NUNCA a backend/data/."""
    import services.gitlab_sync_watermark as wm

    monkeypatch.setattr(wm, "data_dir", lambda: tmp_path)
    assert tmp_path.name in str(wm._path()), f"el store NO esta aislado: {wm._path()}"
    return wm


CTX = SimpleNamespace(
    stacky_project_name="RIPLEY",
    tracker_project="ripley/agenda-web",
    tracker_type="gitlab",
)

_AHORA = datetime.utcnow()


def _iso(minutos_atras=5):
    """Una hora de GitLab, fresca respecto de `utcnow()`. Las marcas tienen que
    quedar dentro de las 24 h de `_EDAD_MAX_MARCA_H` o el modo degrada a completo
    y los casos de este archivo dejarian de probar el camino parcial."""
    return (_AHORA - timedelta(minutes=minutos_atras)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _menos_solapamiento(iso):
    """Lo que el store guarda: el maximo de la tanda menos los 120 s."""
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
    return (d - timedelta(seconds=120)).isoformat(timespec="seconds") + "Z"


class _ProviderConCuenta:
    """Extiende el `_ProviderFalso` de test_plan276_gitlab_sync.py:105-114, que NO
    tiene `get_item` — sin el, el traido de padres cuenta `padres_fallidos` por el
    `except Exception` de gitlab_sync.py:376 y el caso 7 seria un falso verde."""

    name = "gitlab"

    def __init__(self, tandas, padres=None):
        self._tandas = list(tandas)     # una lista de items por corrida
        self.queries = []               # las TrackerQuery emitidas, en orden
        self.gets = []                  # los iid pedidos uno a uno
        self._padres = padres or {}

    def fetch_open_items(self, query):
        self.queries.append(query)
        return list(self._tandas.pop(0)) if self._tandas else []

    def get_item(self, item_id):
        self.gets.append(str(item_id))
        if str(item_id) in self._padres:
            return self._padres[str(item_id)]
        raise LookupError(f"padre {item_id} no deberia pedirse en este caso")


def _issue(iid, id_=None, titulo="T", tipo="Issue", parent=None, estado="opened",
           updated_at=None):
    return {
        "id": str(id_ if id_ is not None else 1000 + int(iid)),
        "iid": str(iid),
        "title": titulo,
        "description": "d",
        "state": estado,
        "labels": [],
        "assignees": [],
        "web_url": f"https://gl.interno/ripley/agenda-web/-/issues/{iid}",
        "updated_at": updated_at or _iso(5),
        "work_item_type": tipo,
        "parent": str(parent) if parent is not None else None,
    }


@pytest.fixture()
def correr(monkeypatch, bd, store):
    """Devuelve (corridas -> resultados, proveedor). Cada llamada es UNA corrida."""
    import services.gitlab_sync as gs

    monkeypatch.setattr(gs, "resolve_project_context", lambda _p: CTX)

    def _fabricar(tandas, padres=None):
        prov = _ProviderConCuenta(tandas, padres=padres)

        def _correr(forzar_full=False):
            return gs.sync_gitlab_tickets("RIPLEY", provider=prov, forzar_full=forzar_full)

        return _correr, prov

    return _fabricar


def _estados(bd):
    from models import Ticket

    return {t.ado_id: t.ado_state for t in bd.session.query(Ticket).all()}


# ───────────────── F5 — los dos invariantes centrales ─────────────────


def test_el_delta_PARCIAL_no_cierra_a_los_ausentes(correr, bd):
    """EL CASO CENTRAL. La tanda de la corrida 2 es PARCIAL NO VACIA: con la tanda
    vacia el `if vistos_external:` de gitlab_sync.py:312 ya corta y el gate no
    discriminaria. Medido contra el codigo de hoy: `removed=2`."""
    tres = [_issue(1), _issue(2), _issue(3)]
    correr_, prov = correr([tres, [_issue(2, titulo="cambio")]])

    r1 = correr_()
    assert r1["created"] == 3
    assert prov.queries[0].updated_after is None
    assert prov.queries[0].state == "open"

    r2 = correr_()
    assert prov.queries[1].updated_after is not None, "la corrida 2 no fue incremental"
    assert prov.queries[1].state == "all"
    assert r2["modo_sync"] == "incremental"
    assert r2["removed"] == 0, "el sync PARCIAL cerro filas por ausencia"
    assert _estados(bd) == {1: "opened", 2: "opened", 3: "opened"}


def test_el_delta_vacio_tampoco_cierra_nada(correr, bd):
    """Complementario, NO gate: pasa tambien sin el plan, porque con `items == []`
    el `if vistos_external:` preexistente ya corta."""
    correr_, _ = correr([[_issue(1), _issue(2), _issue(3)], []])
    correr_()
    r2 = correr_()
    assert r2["removed"] == 0
    assert _estados(bd) == {1: "opened", 2: "opened", 3: "opened"}


def test_el_sync_completo_sigue_cerrando_por_ausencia(correr, bd):
    """La mitad de contraste del caso central: la regla de ausencia sigue VIVA en
    modo completo, sin tocar una linea de su cuerpo."""
    correr_, _ = correr([[_issue(1), _issue(2), _issue(3)], [_issue(1), _issue(2)]])
    correr_()
    r2 = correr_(forzar_full=True)
    assert r2["modo_sync"] == "completo"
    assert r2["removed"] == 1
    assert _estados(bd)[3] == "closed"


def test_un_cerrado_DESCONOCIDO_del_delta_no_crea_fila(correr, bd):
    """R1b / §3.1-bis — la barrera de ESCRITURA. Medido contra el codigo de hoy:
    `created=1` y la fila (77,'closed') creada de la nada."""
    from models import Ticket

    correr_, _ = correr([
        [_issue(1)],
        [_issue(1, titulo="cambio"), _issue(77, estado="closed")],
    ])
    correr_()
    r2 = correr_()
    assert r2["modo_sync"] == "incremental"
    assert r2["created"] == 0, "el delta parcial creo una fila cerrada que no existia"
    assert r2["omitidos_cerrados_desconocidos"] == 1
    assert bd.session.query(Ticket).count() == 1
    assert 77 not in _estados(bd)


def test_un_padre_cerrado_SI_se_trae_aunque_este_la_barrera(correr, bd):
    """La barrera vive en el bucle del LISTADO, nunca en el traido de padres: una
    epica cerrada cuyos hijos quedarian huerfanos SI debe entrar. Es la deuda que
    saldo el Plan 277 F6."""
    padre_cerrado = _issue(99, tipo="Epic", estado="closed")
    correr_, prov = correr(
        [[_issue(1)], [_issue(1, parent=99)]],
        padres={"99": padre_cerrado},
    )
    correr_()
    r2 = correr_()
    assert r2["modo_sync"] == "incremental"
    assert r2["padres_traidos"] == 1
    assert r2["padres_fallidos"] == 0
    assert prov.gets == ["99"]
    assert _estados(bd)[99] == "closed", "el padre cerrado NO se trajo"


# ───────────────── F5 — las seis condiciones de §3.2 ─────────────────


def test_sin_marca_el_primer_sync_es_completo(correr):
    correr_, prov = correr([[_issue(1)]])
    r1 = correr_()
    assert r1["modo_sync"] == "completo"
    assert r1["motivo_modo"] == "sin_marca"
    assert prov.queries[0].updated_after is None


def test_marca_corrupta_degrada_a_completo(correr, store, bd):
    correr_, _ = correr([[_issue(1), _issue(2), _issue(3)], [_issue(1), _issue(2)]])
    correr_()
    store._path().write_text("{no es json", encoding="utf-8")
    r2 = correr_()
    assert r2["modo_sync"] == "completo"
    assert r2["motivo_modo"] == "marca_ilegible"
    # Y la regla de ausencia VUELVE a estar activa: degradar nunca puede
    # significar "sincronizar menos".
    assert r2["removed"] == 1
    assert _estados(bd)[3] == "closed"


def test_marca_vencida_degrada_a_completo(correr, store):
    correr_, _ = correr([[_issue(1)], [_issue(1)], [_issue(1)]])
    correr_()
    # 25 h de antiguedad: pasa `_EDAD_MAX_MARCA_H`.
    store._path().write_text(
        json.dumps({"RIPLEY": {"marca": _iso(25 * 60), "contador": 1}}), encoding="utf-8"
    )
    assert correr_()["motivo_modo"] == "marca_vencida"
    # La marca del FUTURO tambien vence: si no, el delta siguiente vendria vacio
    # para siempre y el tablero se congelaria en silencio.
    store._path().write_text(
        json.dumps({"RIPLEY": {"marca": _iso(-2 * 60), "contador": 1}}), encoding="utf-8"
    )
    assert correr_()["motivo_modo"] == "marca_vencida"


def test_la_cuota_fuerza_una_corrida_completa(correr, store, monkeypatch):
    """LA UNICA PRUEBA REAL de que la flag numerica esta cableada: el guardian
    test_every_non_reserved_flag_is_wired pasa con la key declarada solo en
    config.py, jamas leida."""
    import config as _config_mod

    monkeypatch.setattr(_config_mod.config, "STACKY_GITLAB_SYNC_FULL_CADA_N", 3, raising=False)
    correr_, _ = correr([[_issue(1)]] * 5)

    modos = [correr_()["modo_sync"] for _ in range(5)]
    assert modos == ["completo", "incremental", "incremental", "incremental", "completo"]
    # Tras la corrida de cuota el contador vuelve a 0.
    assert store.leer_marca("RIPLEY")[1] == 0


def test_la_opcion_apagada_deja_el_sync_identico_al_de_hoy(correr, bd, monkeypatch):
    import config as _config_mod

    monkeypatch.setattr(
        _config_mod.config, "STACKY_GITLAB_SYNC_INCREMENTAL_ENABLED", False, raising=False
    )
    correr_, prov = correr([[_issue(1), _issue(2), _issue(3)], [_issue(1), _issue(2)]])
    r1 = correr_()
    r2 = correr_()
    assert r1["modo_sync"] == r2["modo_sync"] == "completo"
    assert r2["motivo_modo"] == "opcion_apagada"
    assert all(q.updated_after is None for q in prov.queries)
    assert all(q.state == "open" for q in prov.queries)
    # La regla de ausencia cierra igual que antes del plan.
    assert r2["removed"] == 1
    assert _estados(bd)[3] == "closed"


def test_el_pedido_explicito_gana_sobre_una_marca_fresca(correr):
    correr_, prov = correr([[_issue(1)], [_issue(1)]])
    correr_()
    r2 = correr_(forzar_full=True)
    assert r2["modo_sync"] == "completo"
    assert r2["motivo_modo"] == "pedido_explicito"
    assert prov.queries[1].updated_after is None


# ───────────────── F5 — la deteccion de cierre por ESTADO ─────────────────


def test_un_issue_cerrado_CONOCIDO_en_el_delta_marca_la_fila_cerrada(correr, bd):
    """§3.1 — con `state="all"` el cierre se captura por el estado propio del
    issue, NO por su ausencia. Y la barrera de §3.1-bis no bloquea este caso."""
    correr_, _ = correr([[_issue(1)], [_issue(1, estado="closed")]])
    correr_()
    r2 = correr_()
    assert r2["modo_sync"] == "incremental"
    assert r2["removed"] == 0
    assert r2["omitidos_cerrados_desconocidos"] == 0
    assert _estados(bd)[1] == "closed"


def test_un_issue_reabierto_vuelve_a_opened(correr, bd):
    correr_, _ = correr([[_issue(1, estado="closed")], [_issue(1, estado="opened")]])
    correr_()
    assert _estados(bd)[1] == "closed"
    correr_()
    assert _estados(bd)[1] == "opened"


# ───────────────── F5 — el reloj y la marca ─────────────────


def test_la_marca_usa_la_hora_de_gitlab_no_la_local(correr, store):
    """R3 y R4. La marca guardada es el max(updated_at) de GitLab menos los 120 s
    de solapamiento, y NO se parece a `utcnow()`."""
    correr_, _ = correr([[
        _issue(1, updated_at="2026-08-01T09:00:00Z"),
        _issue(2, updated_at="2026-08-01T10:00:00Z"),
    ]])
    correr_()
    marca, _contador = store.leer_marca("RIPLEY")
    assert marca == "2026-08-01T09:58:00Z"
    assert not marca.startswith(datetime.utcnow().strftime("%Y-%m-%dT%H:%M"))


def test_un_delta_vacio_no_mueve_la_marca_pero_si_el_contador(correr, store):
    correr_, _ = correr([[_issue(1)], []])
    correr_()
    marca_previa, contador_previo = store.leer_marca("RIPLEY")
    r2 = correr_()
    assert r2["modo_sync"] == "incremental"
    marca, contador = store.leer_marca("RIPLEY")
    assert marca == marca_previa, "un delta vacio movio la marca"
    assert contador == contador_previo + 1


def test_un_completo_posterior_no_hace_retroceder_la_marca(correr, store):
    """R11. En COMPLETO `items` son solo los ABIERTOS: si el cambio mas reciente
    fue sobre un CERRADO, el max de esa tanda es MAS VIEJO que la marca previa."""
    correr_, _ = correr([
        [_issue(1, updated_at=_iso(10))],
        [_issue(1, updated_at=_iso(5))],
        [_issue(1, updated_at=_iso(600))],
    ])
    correr_()
    correr_()
    marca_alta = store.leer_marca("RIPLEY")[0]
    assert marca_alta == _menos_solapamiento(_iso(5))
    correr_(forzar_full=True)
    assert store.leer_marca("RIPLEY")[0] == marca_alta, "la marca RETROCEDIO tras un completo"


# ───────────────── F5 — costo y mecanismo ─────────────────


def test_el_delta_no_dispara_pedidos_de_padres_uno_a_uno(correr):
    correr_, prov = correr([[_issue(1)], [_issue(1, titulo="cambio")]])
    correr_()
    correr_()
    assert prov.gets == []


def test_bytes_recibidos_baja_a_cero_en_estado_estable(correr):
    """K6 — el ahorro se mide solo, sin preguntarle nada a GitLab."""
    correr_, _ = correr([[_issue(1), _issue(2)], []])
    r1 = correr_()
    assert r1["bytes_recibidos"] > 0
    r2 = correr_()
    assert r2["modo_sync"] == "incremental"
    assert r2["bytes_recibidos"] == 0


def test_k1_en_estado_estable_el_delta_trae_cero_items(correr):
    """Este caso prueba el MECANISMO, no el KPI: el 0 lo decide el doble, no
    GitLab. K1 esta declarado como PROYECCION en §1.1."""
    correr_, _ = correr([[_issue(i) for i in range(1, 64)], []])
    r1 = correr_()
    assert r1["fetched"] == 63
    r2 = correr_()
    assert r2["fetched"] == 0
