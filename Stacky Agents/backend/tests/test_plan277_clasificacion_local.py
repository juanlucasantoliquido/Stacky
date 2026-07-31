"""tests/test_plan277_clasificacion_local.py — Plan 277 F4.

QUÉ PRUEBA ESTE ARCHIVO, en una línea: que el operador puede decir "este ticket es
la épica X" y "estos cuelgan de ella" SIN escribir una sola letra en el GitLab de la
empresa, y que ese dato suyo no se pierde nunca.

LOS TRES CASOS QUE HACEN QUE EL ARCHIVO VALGA:
  · 13 — el PATCH no emite NI UNA llamada HTTP al tracker. Es la promesa de la fase.
  · 15 — `_rebuild_tickets_table_if_needed` hace `DROP TABLE tickets`; sin las dos
         columnas en sus TRES listas, la clasificación del operador desaparecía sin
         error y sin log. El assert es de PRESENCIA con el dato sembrado antes.
  · 17 — `_legacy_payload()` sigue con 16 claves exactas (contrato del plan 218 F5).

AISLAMIENTO DE LA BD (desvío declarado): `db.py` construye el engine AL IMPORTARSE y
una sola vez por proceso, así que una base por test es imposible para todo lo que
pase por `session_scope` o por el cliente Flask. Se usa una base temporal por MÓDULO
(`tmp_path_factory`) y las tablas se limpian por test. Lo que importa —no tocar la
base REAL del operador, 174 MB— se verifica con un assert explícito sobre la URL del
engine. Es el mismo patrón que `test_plan276_hierarchy_gitlab.py`.
"""
from __future__ import annotations

import sys
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

_FLAG = "STACKY_GITLAB_HIERARCHY_LOCAL_CLASSIFY_ENABLED"


@pytest.fixture(scope="module")
def _bd_temporal(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("plan277f4") / "p277f4.db"
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{ruta.as_posix()}"
    os.environ["STACKY_SKIP_STARTUP_SYNC"] = "1"
    import db as db_mod

    url = str(db_mod.engine.url)
    assert "pytest" in url and url.endswith("p277f4.db"), (
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


def _fila(ado_id, external_id, *, tipo="Issue", parent=None, local_tipo=None,
          local_padre=None, tracker="gitlab", stacky="RIPLEY"):
    return {
        "ado_id": ado_id, "external_id": external_id, "project": "ripley/agenda-web",
        "stacky_project_name": stacky, "tracker_type": tracker,
        "title": f"issue {ado_id}", "ado_state": "opened",
        "work_item_type": tipo, "parent_ado_id": parent,
        "local_work_item_type": local_tipo, "local_parent_iid": local_padre,
    }


def _sembrar(filas) -> list[int]:
    """Inserta y devuelve los `id` de PK, en el mismo orden."""
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


def _leer(ado_id):
    from db import session_scope
    from models import Ticket

    with session_scope() as s:
        t = s.query(Ticket).filter(Ticket.ado_id == ado_id).one()
        return SimpleNamespace(
            work_item_type=t.work_item_type,
            parent_ado_id=t.parent_ado_id,
            local_work_item_type=t.local_work_item_type,
            local_parent_iid=t.local_parent_iid,
        )


def _patch(client, ticket_id, body):
    return client.patch(f"/api/tickets/{ticket_id}/hierarchy", json=body)


def _provider():
    """Provider real con el transporte mockeado — cero red (igual que F2/F3)."""
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


def _payload(iid, *, labels=None, id_=None):
    return {
        "id": id_ if id_ is not None else 1000 + iid,
        "iid": iid,
        "title": f"issue {iid}",
        "description": "<p>d</p>",
        "state": "opened",
        "labels": list(labels or []),
        "assignees": [],
        "web_url": f"https://gl.interno/ripley/agenda-web/-/issues/{iid}",
        "updated_at": "2026-07-31T00:00:00Z",
    }


def _sync(monkeypatch, payloads):
    import services.gitlab_sync as gs

    prov = _provider()
    items = [prov._normalize_issue(p) for p in payloads]
    monkeypatch.setattr(gs, "resolve_project_context", lambda _p: CTX)

    class _ProviderFalso:
        name = "gitlab"

        def fetch_open_items(self, query):
            return list(items)

    return gs.sync_gitlab_tickets("RIPLEY", provider=_ProviderFalso())


# ── Casos 1-2: las columnas existen y el ALTER es idempotente ───────────────

def test_01_las_dos_columnas_existen_tras_init_db(_bd_temporal):
    from sqlalchemy import text

    import db as db_mod

    with db_mod.engine.connect() as conn:
        columnas = {r[1] for r in conn.execute(text("PRAGMA table_info(tickets)")).fetchall()}
    # SEMBRADO: la lectura del PRAGMA de verdad devolvió la tabla.
    assert "ado_id" in columnas, columnas
    assert {"local_work_item_type", "local_parent_iid"} <= columnas, columnas


def test_02_correr_la_migracion_dos_veces_no_levanta(_bd_temporal):
    from sqlalchemy import text

    import db as db_mod

    db_mod._migrate_add_columns()
    db_mod._migrate_add_columns()

    with db_mod.engine.connect() as conn:
        columnas = {r[1] for r in conn.execute(text("PRAGMA table_info(tickets)")).fetchall()}
    assert {"local_work_item_type", "local_parent_iid"} <= columnas, columnas


# ── Casos 3-8: el endpoint ──────────────────────────────────────────────────

def test_03_el_patch_escribe_la_local_y_no_toca_la_remota(client):
    [tid] = _sembrar([_fila(7, 1007, tipo="Issue")])

    resp = _patch(client, tid, {"work_item_type": "Epic"})

    assert resp.status_code == 200, resp.get_json()
    fila = _leer(7)
    assert fila.local_work_item_type == "Epic"
    assert fila.work_item_type == "Issue", (
        "la clasificación local pisó la columna que escribe el tracker"
    )
    # Echo-back: el control tiene de dónde precargarse (v2/C3).
    assert resp.get_json()["ticket"]["local_work_item_type"] == "Epic", resp.get_json()


def test_04_auto_padre_da_400(client):
    [tid] = _sembrar([_fila(7, 1007)])

    resp = _patch(client, tid, {"parent_iid": 7})

    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["error"] == "validation", resp.get_json()
    assert _leer(7).local_parent_iid is None, "el auto-padre se guardó igual"


def test_05_un_ciclo_da_409(client):
    """A→B→A. Sin esta guarda, `get_hierarchy` arma `d["children"].append(d)` y
    `jsonify` levanta `ValueError: Circular reference detected` ⇒ 500 y el grafo
    entero en blanco."""
    ids = _sembrar([_fila(1, 1001), _fila(2, 1002, parent=1)])
    id_uno = ids[0]

    # SEMBRADO: colgar 1 de un ticket que NO cierra ciclo sí se acepta. Sin esto,
    # un 409 constante (endpoint roto) también pasaría el assert de abajo.
    _sembrar([_fila(9, 1009)])
    assert _patch(client, id_uno, {"parent_iid": 9}).status_code == 200

    resp = _patch(client, id_uno, {"parent_iid": 2})   # 1 → 2 → 1

    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["error"] == "cycle", resp.get_json()
    assert _leer(1).local_parent_iid == 9, "el ciclo se guardó igual y pisó lo anterior"


def test_06_null_borra_la_local_con_el_valor_sembrado_antes(client):
    """Un assert de ausencia que nunca vio el dato guardado pasa por accidente."""
    [tid] = _sembrar([_fila(7, 1007, local_tipo="Epic", local_padre=42)])
    # POSITIVO PRIMERO: el valor ESTABA.
    assert _leer(7).local_work_item_type == "Epic"

    resp = _patch(client, tid, {"work_item_type": None})

    assert resp.status_code == 200, resp.get_json()
    assert _leer(7).local_work_item_type is None
    assert _leer(7).local_parent_iid == 42, (
        "borrar el tipo borró también el padre: el PATCH no es parcial"
    )


def test_07_una_clave_ausente_no_se_toca(client):
    [tid] = _sembrar([_fila(7, 1007, local_tipo="Epic", local_padre=42)])

    resp = _patch(client, tid, {"work_item_type": "Bug"})

    assert resp.status_code == 200, resp.get_json()
    fila = _leer(7)
    assert fila.local_work_item_type == "Bug"
    assert fila.local_parent_iid == 42, "un campo ausente se borró por omisión"


def test_08_ticket_inexistente_da_404(client):
    resp = _patch(client, 999999, {"work_item_type": "Epic"})
    assert resp.status_code == 404, resp.get_json()
    assert resp.get_json()["error"] == "not_found", resp.get_json()


# ── Casos 9-11: la precedencia en el sync ───────────────────────────────────

def test_09_el_sync_usa_la_local_cuando_gitlab_no_dijo_nada(monkeypatch):
    """EL CASO DEL OPERADOR: los 53 issues de RIPLEY no tienen ninguna etiqueta."""
    _sembrar([_fila(7, 1007, tipo="Issue", local_tipo="Epic", local_padre=3)])

    resultado = _sync(monkeypatch, [_payload(7, labels=[])])

    fila = _leer(7)
    assert fila.work_item_type == "Epic", fila
    assert fila.parent_ado_id == 3, fila
    assert resultado["usados_local_tipo"] == 1, resultado
    assert resultado["usados_local_padre"] == 1, resultado


def test_10_gitlab_pisa_a_la_local_pero_la_local_sigue_guardada(monkeypatch):
    """§3.2 — GitLab es el sistema de registro. Pero el dato del operador NO se
    destruye: se cuenta como superseded y queda en su columna."""
    _sembrar([_fila(7, 1007, tipo="Issue", local_tipo="Epic")])

    resultado = _sync(monkeypatch, [_payload(7, labels=["type::bug"])])

    fila = _leer(7)
    assert fila.work_item_type == "Bug", fila
    assert resultado["superseded_tipo"] == 1, resultado
    assert resultado["usados_local_tipo"] == 0, resultado
    assert fila.local_work_item_type == "Epic", (
        "el sync BORRÓ la clasificación del operador; contradice el riesgo R6 del plan"
    )


def test_11_primera_aparicion_sin_fila_no_revienta(monkeypatch):
    """El caso borde declarado: `fila is None` y no hay nada que aplicar. La
    clasificación local se aplica desde el sync SIGUIENTE."""
    resultado = _sync(monkeypatch, [_payload(8, labels=[])])

    assert resultado["created"] == 1, resultado
    assert resultado["usados_local_tipo"] == 0, resultado
    assert resultado["usados_local_padre"] == 0, resultado
    assert resultado["superseded_tipo"] == 0 and resultado["superseded_padre"] == 0, resultado
    assert _leer(8).work_item_type == "Issue"


# ── Caso 12: kill-switch REAL (una flag registrada puede estar muerta) ──────

def test_12_con_la_flag_apagada_el_sync_ignora_y_el_patch_da_403(client, monkeypatch):
    import config as cmod

    [tid] = _sembrar([_fila(7, 1007, tipo="Issue", local_tipo="Epic", local_padre=3)])

    # SEMBRADO: con la flag ENCENDIDA este mismo dato SÍ se aplica (test 09). Acá
    # se apaga y tiene que quedar inerte.
    monkeypatch.setattr(cmod.config, _FLAG, False, raising=False)

    resultado = _sync(monkeypatch, [_payload(7, labels=[])])
    fila = _leer(7)
    assert fila.work_item_type == "Issue", "la flag no gatea el sync: el rollback es ficticio"
    assert fila.parent_ado_id is None, fila
    assert resultado["usados_local_tipo"] == 0, resultado
    assert fila.local_work_item_type == "Epic", "apagar la flag borró el dato del operador"

    resp = _patch(client, tid, {"work_item_type": "Bug"})
    assert resp.status_code == 403, resp.get_json()
    cuerpo = resp.get_json()
    assert cuerpo["error"] == "flag_off", cuerpo
    assert _FLAG in cuerpo.get("message", "") or cuerpo.get("flag") == _FLAG, cuerpo
    assert _leer(7).local_work_item_type == "Epic", "el 403 escribió igual"


# ── Caso 13: LA PROMESA CENTRAL — cero HTTP contra el sistema del operador ──

def test_13_el_patch_no_hace_ninguna_llamada_a_gitlab(client, monkeypatch):
    from services.gitlab_client import GitLabClient

    llamadas = []

    def _espia(self, *a, **kw):
        llamadas.append((a, kw))
        return ({}, {})

    monkeypatch.setattr(GitLabClient, "_request", _espia, raising=True)

    [tid] = _sembrar([_fila(7, 1007)])
    resp = _patch(client, tid, {"work_item_type": "Epic", "parent_iid": 3})

    assert resp.status_code == 200, resp.get_json()
    assert llamadas == [], f"el PATCH tocó el GitLab del operador: {llamadas}"

    # SEMBRADO: el espía FUNCIONA. Un contador que nunca vio un positivo da 0
    # también cuando el monkeypatch no tomó efecto.
    GitLabClient._request(object(), "GET", "/version")
    assert len(llamadas) == 1, "el espía no intercepta: el assert de arriba pasaba solo"


# ── Caso 14: idempotencia, con los TRES asserts juntos ─────────────────────

def test_14_segunda_corrida_sin_cambios_no_crea_ni_actualiza(monkeypatch):
    from db import session_scope
    from models import Ticket

    payloads = [_payload(7, labels=["type::funcional", "epic::3"]), _payload(8, labels=[])]

    primera = _sync(monkeypatch, payloads)
    with session_scope() as s:
        filas_1 = s.query(Ticket).count()
    assert primera["created"] == 2, primera   # SEMBRADO: la 1ª corrida SÍ escribió

    segunda = _sync(monkeypatch, payloads)
    with session_scope() as s:
        filas_2 = s.query(Ticket).count()

    # Los tres juntos: cada uno solo pasa por accidente.
    assert segunda["created"] == 0, segunda
    assert segunda["updated"] == 0, segunda
    assert filas_2 == filas_1 == 2, (filas_1, filas_2)


# ── Caso 15 (BLOQUEANTE v2/C2): el rebuild que borraba la clasificación ────

def test_15_el_rebuild_de_la_tabla_conserva_las_dos_columnas(_bd_temporal):
    """`_rebuild_tickets_table_if_needed` hace `DROP TABLE tickets` con la lista de
    columnas HARDCODEADA en tres lugares. Si falta una, el dato del operador
    desaparece sin error y sin log."""
    from sqlalchemy import text

    import db as db_mod

    _sembrar([_fila(7, 1007, local_tipo="Epic", local_padre=42)])
    # POSITIVO PRIMERO: el dato ESTABA antes del rebuild.
    antes = _leer(7)
    assert (antes.local_work_item_type, antes.local_parent_iid) == ("Epic", 42)

    with db_mod.engine.connect() as conn:
        # Forzar el rebuild: la función se dispara cuando FALTA este índice, que es
        # exactamente el perfil de la base vieja del operador.
        conn.execute(text("DROP INDEX IF EXISTS ux_tickets_stacky_tracker_external"))
        conn.commit()
        indices = {r[1] for r in conn.execute(text("PRAGMA index_list(tickets)")).fetchall()}
        assert "ux_tickets_stacky_tracker_external" not in indices, (
            "el índice no se borró: el rebuild NO se va a disparar y el test no probaría nada"
        )

        db_mod._rebuild_tickets_table_if_needed(conn)

        indices = {r[1] for r in conn.execute(text("PRAGMA index_list(tickets)")).fetchall()}
        assert "ux_tickets_stacky_tracker_external" in indices, (
            "el rebuild no corrió: sin él este test es un no-op"
        )

    despues = _leer(7)
    assert despues.local_work_item_type == "Epic", "el rebuild borró el tipo local"
    assert despues.local_parent_iid == 42, "el rebuild borró el padre local"


# ── Casos 16-18: el echo-back y el contrato de las 16 claves ───────────────

def test_16_to_dict_canonico_trae_las_dos_claves_con_su_valor(_bd_temporal, monkeypatch):
    import config as cmod
    from db import session_scope
    from models import Ticket

    monkeypatch.setattr(cmod.config, "STACKY_CANONICAL_VOCABULARY_ENABLED", True, raising=False)
    _sembrar([_fila(7, 1007, local_tipo="Epic", local_padre=42)])

    with session_scope() as s:
        d = s.query(Ticket).filter(Ticket.ado_id == 7).one().to_dict()

    assert d["local_work_item_type"] == "Epic", d
    assert d["local_parent_iid"] == 42, d


def test_17_legacy_payload_sigue_con_16_claves_exactas(_bd_temporal):
    """El contrato byte-idéntico del plan 218 F5. El arreglo del echo-back no puede
    romperlo: por eso las dos claves van SOLO en el dict canónico."""
    from db import session_scope
    from models import Ticket

    _sembrar([_fila(7, 1007, local_tipo="Epic", local_padre=42)])
    with session_scope() as s:
        legacy = s.query(Ticket).filter(Ticket.ado_id == 7).one()._legacy_payload()

    assert len(legacy) == 16, sorted(legacy)
    assert "local_work_item_type" not in legacy, sorted(legacy)
    assert "local_parent_iid" not in legacy, sorted(legacy)


def test_18_el_grafo_devuelve_los_dos_campos_en_cada_ticket(client, monkeypatch):
    """`get_hierarchy` construye cada nodo con `t.to_dict()`: es el consumidor real
    del que se precarga el control."""
    import api.tickets as t

    _sembrar([
        _fila(1, 1001, tipo="Epic", local_tipo="Epic"),
        _fila(2, 1002, parent=1, local_padre=1),
    ])
    monkeypatch.setattr(t, "resolve_project_context", lambda **kw: CTX)

    body = client.get("/api/tickets/hierarchy?project=RIPLEY").get_json()

    nodos = body["epics"] + [h for e in body["epics"] for h in e["children"]] + body["orphans"]
    assert nodos, body
    for nodo in nodos:
        assert "local_work_item_type" in nodo, nodo
        assert "local_parent_iid" in nodo, nodo
    por_id = {n["ado_id"]: n for n in nodos}
    assert por_id[1]["local_work_item_type"] == "Epic", por_id[1]
    assert por_id[2]["local_parent_iid"] == 1, por_id[2]
