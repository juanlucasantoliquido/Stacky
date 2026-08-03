"""tests/test_epic_from_brief_idempotencia.py — idempotencia REAL en el servidor.

`POST /api/tickets/epics/from-brief` (api/tickets.py:7958) publicaba SIEMPRE que lo
llamaran: ni hash del brief, ni execution_id, ni dedupe. Toda la defensa contra la
epica duplicada vivia en un `if` del navegador (EpicFromBriefModal.tsx:223), y ese
`if` se caia solo con que el sello llegara como string.

La clave de idempotencia es el `execution_id`, materializado en el SELLO que ya
existe (`AgentExecution.metadata_dict["epic_ado_id"]` / `["issue_ado_id"]`, escrito
por services/epic_autopublish.py:280-282). NO el hash del brief: regenerar con el
mismo brief es un caso LEGITIMO —el operador reintenta cuando la primera epica
salio narrada (EpicFromBriefModal.tsx:58, boton "Volver" en :640)— y un hash lo
deduplicaria MAL, devolviendo la epica basura. El caso 06 es el gate de esa
decision.

El arbitro de concurrencia es el CLAIM ATOMICO que ya usa el post-hook
(epic_autopublish._claim_once:121-144, UN solo UPDATE condicional). Endpoint y
post-hook son dos escritores del MISMO hecho: comparten claim, asi que solo uno
publica. El caso 05 es ese gate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


_EPIC_HTML = "<h1>Épica de prueba</h1><h2>RF-001 — algo</h2><p>cuerpo</p>"

# Secuencia de ids sentinela compartida por todo el archivo (ver `_nueva_run`).
_SEQ = [-700]


class _ProviderQueCuenta:
    """Forma REAL de `GitLabTrackerProvider.create_item`: `_normalize_issue`
    (gitlab_provider.py:130-150) estringa los ids y devuelve `id` (global) e `iid`."""

    name = "gitlab"

    def __init__(self):
        self.creados = 0

    def create_item(self, item):
        self.creados += 1
        iid = 100 + self.creados
        return {
            "id": str(4000 + self.creados),
            "iid": str(iid),
            "title": "Épica de prueba",
            "web_url": f"https://gl.interno/ripley/agenda-web/-/issues/{iid}",
        }

    def item_url(self, item_id):
        return f"https://gl.interno/ripley/agenda-web/-/issues/{item_id}"


class _AdoQueCuenta:
    """Camino ADO: `create_work_item` devuelve el JSON crudo de ADO (id int)."""

    def __init__(self):
        self.creados = 0

    def create_work_item(self, **kw):
        self.creados += 1
        wid = 900 + self.creados
        return {"id": wid, "rev": 1,
                "fields": {"System.Title": "Épica de prueba"},
                "_links": {"html": {"href": f"https://dev.azure.com/wi/{wid}"}}}

    def work_item_url(self, wid):
        return f"https://dev.azure.com/wi/{wid}"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """App + BD aislada + una run de brief lista para publicar.

    `DATABASE_URL` va ANTES de `create_app()`: sin eso `create_all` corre contra la
    BD REAL del operador (backend/data/stacky_agents.db, 184 MB).
    """
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'idem.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")

    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)

    import api.tickets as t

    # El brief se guarda en disco (Agentes/outputs/...): fuera del test.
    monkeypatch.setattr(t, "_epic_brief_save", lambda *a, **k: None)

    def _nueva_run(brief="BRIEF X", metadata=None):
        """Crea Ticket + AgentExecution reales y devuelve el execution_id.

        `ado_id`/`external_id` salen de una SECUENCIA de módulo, no de un literal:
        `db.py` construye el engine AL IMPORTARSE, así que el `DATABASE_URL` que
        gana es el del PRIMER test del archivo y todos comparten esa misma sqlite.
        Con un literal fijo, el segundo test explota con IntegrityError contra
        `ux_tickets_stacky_tracker_external` — un fallo del fixture, no del código.
        """
        from db import session_scope
        from models import AgentExecution, Ticket

        _SEQ[0] -= 1
        with session_scope() as session:
            ticket = Ticket(ado_id=_SEQ[0], external_id=_SEQ[0], project="ripley/agenda-web",
                            stacky_project_name="RIPLEY", tracker_type="gitlab",
                            title="run de brief", stacky_status="running")
            session.add(ticket)
            session.flush()
            row = AgentExecution(ticket_id=ticket.id, agent_type="business",
                                 status="completed", started_by="test@test.com",
                                 output=_EPIC_HTML)
            row.input_context = [{"id": "brief", "content": brief}]
            row.metadata_dict = metadata or {}
            session.add(row)
            session.flush()
            return row.id

    class _Entorno:
        def __init__(self):
            self.client = app.test_client()
            self.nueva_run = _nueva_run
            self.tickets = t

        def post(self, **extra):
            cuerpo = {"title": "", "description_html": _EPIC_HTML, "brief": "BRIEF X",
                      "project_name": "RIPLEY", "confirm": True}
            cuerpo.update(extra)
            return self.client.post("/api/tickets/epics/from-brief", json=cuerpo)

        def sello(self, execution_id):
            from db import session_scope
            from models import AgentExecution

            with session_scope() as session:
                row = session.get(AgentExecution, execution_id)
                return dict(row.metadata_dict or {})

    yield _Entorno()


def _gitlab(entorno, monkeypatch):
    prov = _ProviderQueCuenta()
    monkeypatch.setattr(entorno.tickets, "_provider_for_ticket", lambda **kw: prov)
    return prov


# ── El gate binario ───────────────────────────────────────────────────────────

def test_01_dos_post_identicos_dejan_UNA_epica(entorno, monkeypatch):
    """EL GATE: dos POST idénticos consecutivos ⇒ UNA sola creación en el tracker."""
    prov = _gitlab(entorno, monkeypatch)
    execution_id = entorno.nueva_run()

    primera = entorno.post(execution_id=execution_id)
    segunda = entorno.post(execution_id=execution_id)

    assert prov.creados == 1, (
        f"el endpoint creó {prov.creados} épicas en el tracker con el mismo "
        f"execution_id; la segunda llamada tenía que ser idempotente "
        f"(status1={primera.status_code}, status2={segunda.status_code})"
    )


def test_02_el_repetido_devuelve_200_con_la_epica_existente(entorno, monkeypatch):
    """El repetido NO es un error: 200 con la épica que YA existe y el shape intacto."""
    _gitlab(entorno, monkeypatch)
    execution_id = entorno.nueva_run()

    primera = entorno.post(execution_id=execution_id)
    segunda = entorno.post(execution_id=execution_id)

    assert primera.status_code == 201, primera.get_data(as_text=True)
    assert segunda.status_code == 200, (
        f"el repetido devolvió {segunda.status_code}; se pidió 200 con la épica "
        f"existente, ni 409 ni 500: {segunda.get_data(as_text=True)}"
    )
    d2 = segunda.get_json()
    # El shape que consume el frontend (endpoints.ts:474) NO se rompe.
    for clave in ("ok", "ado_id", "work_item_type", "title", "url"):
        assert clave in d2, f"falta '{clave}' en la respuesta del repetido: {d2}"
    assert d2["ok"] is True
    assert d2["already_published"] is True
    assert d2["ado_id"] == primera.get_json()["ado_id"], "devolvió OTRA épica"


def test_03_la_primera_publicacion_no_se_marca_como_repetida(entorno, monkeypatch):
    prov = _gitlab(entorno, monkeypatch)
    execution_id = entorno.nueva_run()

    res = entorno.post(execution_id=execution_id)

    assert res.status_code == 201 and prov.creados == 1
    assert res.get_json().get("already_published") in (False, None)


def test_04_el_sello_queda_escrito_para_que_lo_vea_el_post_hook(entorno, monkeypatch):
    """El endpoint sella `epic_ado_id` en la MISMA clave que el post-hook lee
    (epic_autopublish.py:326-328), o el post-hook publicaría una segunda."""
    _gitlab(entorno, monkeypatch)
    execution_id = entorno.nueva_run()

    res = entorno.post(execution_id=execution_id)

    md = entorno.sello(execution_id)
    assert md.get("epic_ado_id") == res.get_json()["ado_id"]
    assert isinstance(md.get("epic_ado_id"), int), (
        f"el sello quedó {type(md.get('epic_ado_id')).__name__}: el guard del modal "
        f"y el del post-hook lo comparan como número"
    )


# ── Concurrencia ──────────────────────────────────────────────────────────────

def test_05_si_el_post_hook_ya_tomo_el_claim_el_endpoint_no_publica(entorno, monkeypatch):
    """Dos escritores del MISMO hecho comparten el claim atómico. Si el post-hook lo
    tomó primero (está publicando), el endpoint NO puede crear una segunda épica."""
    prov = _gitlab(entorno, monkeypatch)
    execution_id = entorno.nueva_run()

    from services import epic_autopublish

    assert epic_autopublish._claim(execution_id) is True, "el claim de arranque falló"

    res = entorno.post(execution_id=execution_id)

    assert prov.creados == 0, (
        "el endpoint publicó pese a que otro escritor tenía el claim tomado: "
        "eso es exactamente la épica duplicada"
    )
    assert res.status_code in (200, 409), res.get_data(as_text=True)


def test_06_otra_run_con_el_MISMO_brief_si_publica(entorno, monkeypatch):
    """La clave es el execution_id, NO el hash del brief. Regenerar tras una épica
    narrada es legítimo y TIENE que volver a publicar."""
    prov = _gitlab(entorno, monkeypatch)
    run_a = entorno.nueva_run(brief="MISMO BRIEF")
    run_b = entorno.nueva_run(brief="MISMO BRIEF")

    entorno.post(execution_id=run_a, brief="MISMO BRIEF")
    entorno.post(execution_id=run_b, brief="MISMO BRIEF")

    assert prov.creados == 2, (
        "dos generaciones distintas del mismo brief quedaron deduplicadas: "
        "el operador que reintenta se queda con la épica vieja"
    )


# ── Backward-compat ───────────────────────────────────────────────────────────

def test_07_ado_dos_post_identicos_tambien_dejan_una(entorno, monkeypatch):
    """El camino ADO no cambia de comportamiento… salvo que ahora también es idempotente."""
    ado = _AdoQueCuenta()
    monkeypatch.setattr(entorno.tickets, "_provider_for_ticket", lambda **kw: None)
    monkeypatch.setattr(entorno.tickets, "_ado_client_for_ticket", lambda **kw: ado)
    execution_id = entorno.nueva_run()

    primera = entorno.post(execution_id=execution_id, project_name="ProyADO")
    segunda = entorno.post(execution_id=execution_id, project_name="ProyADO")

    assert primera.status_code == 201 and segunda.status_code == 200
    assert ado.creados == 1, f"ADO creó {ado.creados} épicas"
    assert primera.get_json()["ado_id"] == 901, "el id de ADO dejó de ser el que era"


def test_08_sin_execution_id_publica_como_siempre(entorno, monkeypatch):
    """Backward-compat DURA: un cliente viejo (o un script) que no manda
    execution_id sigue publicando 201, sin idempotencia. Está documentado."""
    prov = _gitlab(entorno, monkeypatch)

    res = entorno.post()

    assert res.status_code == 201, res.get_data(as_text=True)
    assert prov.creados == 1


def test_09_confirm_falso_sigue_siendo_400(entorno, monkeypatch):
    """El human-in-the-loop no se relaja: sigue mandando antes que la idempotencia."""
    prov = _gitlab(entorno, monkeypatch)
    execution_id = entorno.nueva_run()

    res = entorno.post(execution_id=execution_id, confirm=False)

    assert res.status_code == 400 and res.get_json()["error"] == "confirmation_required"
    assert prov.creados == 0
