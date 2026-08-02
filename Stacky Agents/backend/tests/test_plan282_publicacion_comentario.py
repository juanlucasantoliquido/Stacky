"""Plan 282 F1 — el comentario del agente se publica en el tracker del TICKET.

Los 7 casos corren contra `publish_from_execution` REAL (no contra una copia del
publicador): se falsean la sesion de BD, el HTML de disco y la persistencia, pero
el dedupe por sha, el dedupe por marcador, la inyeccion del marcador y la
resolucion del cliente son los del modulo de produccion.

NO tocan la base del operador: `session_scope` esta monkeypatcheado.
"""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from pathlib import Path

import pytest


# ── Dobles minimos ────────────────────────────────────────────────────────────


class _TicketFalso:
    def __init__(self, *, tracker_type, ado_id=1115, ticket_id=7,
                 stacky_project_name="RIPLEY", project="grupo/proyecto"):
        self.id = ticket_id
        self.ado_id = ado_id
        self.tracker_type = tracker_type
        self.stacky_project_name = stacky_project_name
        self.project = project


class _EjecucionFalsa:
    def __init__(self, ticket_id=7):
        self.ticket_id = ticket_id
        self.html_output_path = None
        self.metadata_dict = {}
        self.duration_ms = 0


class _QueryFalsa:
    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def first(self):
        return None          # nunca hay dedupe previo por contenido


class _SesionFalsa:
    def __init__(self, exec_row, ticket_row):
        self._exec = exec_row
        self._ticket = ticket_row

    def get(self, modelo, _id):
        return self._ticket if modelo.__name__ == "Ticket" else self._exec

    def query(self, *a, **k):
        return _QueryFalsa()


class _ProviderGitLabFalso:
    """Forma REAL de GitLabTrackerProvider: post_comment de DOS argumentos."""

    def __init__(self, *, ya_existe=False, explota=None):
        self.llamadas: list[tuple] = []
        self._ya_existe = ya_existe
        self._explota = explota

    def post_comment(self, item_id: str, body_html: str) -> dict:
        self.llamadas.append((item_id, body_html))
        if self._explota is not None:
            raise self._explota
        return {"id": 99, "body": body_html}

    def comment_exists(self, item_id: str, marker: str) -> bool:
        return self._ya_existe


class _ClienteAdoFalso:
    """Forma REAL de AdoClient: post_comment de TRES posicionales."""

    def __init__(self):
        self.llamadas: list[tuple] = []

    def post_comment(self, ado_id, html, content_format):
        self.llamadas.append((ado_id, html, content_format))
        return {"id": 4242}

    def comment_exists(self, ado_id, marker):
        return None


# ── Arnes comun ───────────────────────────────────────────────────────────────


def _preparar(monkeypatch, tmp_path: Path, ticket):
    """Deja `publish_from_execution` ejecutable sin BD ni disco del operador."""
    from services import agent_html_output as html_io
    from services import ado_publisher

    ruta = tmp_path / "comment.html"
    ruta.write_text("<p>analisis tecnico</p>", encoding="utf-8")
    salida = html_io.HtmlOutput(
        path=ruta, html="<p>analisis tecnico</p>", size_bytes=23,
        meta=None, ado_id=ticket.ado_id,
    )

    @contextmanager
    def _scope():
        yield _SesionFalsa(_EjecucionFalsa(ticket.id), ticket)

    persistidos: list = []

    def _persist(result, **_kw):
        persistidos.append(result)
        return result

    monkeypatch.setattr(ado_publisher, "session_scope", _scope)
    monkeypatch.setattr(ado_publisher, "_emit_and_persist", _persist)
    monkeypatch.setattr(ado_publisher, "_agent_type_for_execution", lambda _e: None)
    monkeypatch.setattr(ado_publisher, "_increment_idempotent_replay_counter",
                        lambda **_k: None)
    monkeypatch.setattr(html_io, "read_and_validate", lambda *_a, **_k: salida)
    monkeypatch.setattr(ado_publisher.config, "STACKY_ADO_RUN_FOOTER_ENABLED", False,
                        raising=False)
    return persistidos


def _con_provider_gitlab(monkeypatch, provider):
    from services import tracker_provider
    monkeypatch.setattr(tracker_provider, "get_tracker_provider",
                        lambda *_a, **_k: provider)


# ── Caso 1 — ADO primero: el camino de hoy no cambia ──────────────────────────


def test_ado_sigue_publicando_igual_que_hoy(monkeypatch, tmp_path):
    from services import ado_publisher, project_context
    from services.comment_publish_router import resolve_comment_publisher

    # El proyecto tiene que ser uno REALMENTE de ADO. Con el default "RIPLEY"
    # (que es GitLab) este test afirmaba que la columna mentirosa manda sobre el
    # proyecto: congelaba como verde el defecto que mata el plan 286.
    ticket = _TicketFalso(tracker_type="azure_devops",
                          stacky_project_name="RSPACIFICO")
    _preparar(monkeypatch, tmp_path, ticket)
    cliente = _ClienteAdoFalso()
    monkeypatch.setattr(project_context, "build_ado_client", lambda *_a, **_k: cliente)

    # El router clasifica ADO como ADO y devuelve el cliente de siempre.
    pub = resolve_comment_publisher(ticket)
    assert pub.kind == "ado_client"
    assert pub.tracker_type == "azure_devops"
    assert pub.handle is cliente

    res = ado_publisher.publish_from_execution(11, triggered_by="test")
    assert res.ok is True and res.status == "ok"
    assert res.error_kind is None, "el camino ADO no clasifica errores donde no los hay"
    # La llamada sigue siendo de TRES posicionales, con el marcador inyectado.
    assert len(cliente.llamadas) == 1
    ado_id, html, fmt = cliente.llamadas[0]
    assert ado_id == 1115 and fmt == "html"
    assert "stacky-comment:ado=1115" in html
    assert res.comment_id == 4242


# ── Caso 2 — GitLab publica de verdad ─────────────────────────────────────────


def test_gitlab_publica_por_post_comment(monkeypatch, tmp_path):
    from services import ado_publisher

    ticket = _TicketFalso(tracker_type="gitlab")
    _preparar(monkeypatch, tmp_path, ticket)
    provider = _ProviderGitLabFalso()
    _con_provider_gitlab(monkeypatch, provider)

    res = ado_publisher.publish_from_execution(11, triggered_by="test")

    assert res.ok is True, f"no publico: {res.reason}"
    assert res.status == "ok"
    assert len(provider.llamadas) == 1, "post_comment no se llamo exactamente una vez"
    item_id, body = provider.llamadas[0]
    assert item_id == "1115", "el item_id debe ser el iid del issue, como string"
    assert "stacky-comment:ado=1115" in body, "falta el marcador de idempotencia"
    assert res.comment_id == 99


# ── Caso 3 — idempotencia: la que YA existe, no una nueva ─────────────────────


def test_gitlab_no_duplica_si_el_marcador_ya_existe(monkeypatch, tmp_path):
    from services import ado_publisher

    ticket = _TicketFalso(tracker_type="gitlab")
    _preparar(monkeypatch, tmp_path, ticket)
    provider = _ProviderGitLabFalso(ya_existe=True)
    _con_provider_gitlab(monkeypatch, provider)

    res = ado_publisher.publish_from_execution(11, triggered_by="test")

    assert res.status == "idempotent_replay"
    assert res.reason == "ado_marker_exists", (
        "debe salir por el dedupe por marcador que YA existe en el publicador, "
        "no por un skip nuevo"
    )
    assert provider.llamadas == [], "se publico igual: la idempotencia no corto"


# ── Caso 4 — un tracker sin publicador no revienta ────────────────────────────


def test_tracker_sin_publicador_no_revienta(monkeypatch, tmp_path):
    from services import ado_publisher

    ticket = _TicketFalso(tracker_type="mantis")
    _preparar(monkeypatch, tmp_path, ticket)

    res = ado_publisher.publish_from_execution(11, triggered_by="test")

    assert res.ok is False and res.status == "failed"
    assert res.error_kind == "publisher_unavailable"
    assert "mantis" in (res.reason or "")
    assert "Azure DevOps" not in (res.reason or ""), (
        "no puede disfrazarse de fallo de ADO: el tracker es otro"
    )


# ── Caso 5 — el fallo del tracker se clasifica, no se disfraza ────────────────


def test_el_fallo_del_tracker_se_clasifica_y_no_cae_en_exception_generica(
    monkeypatch, tmp_path,
):
    from services import ado_publisher
    from services.tracker_provider import TrackerApiError

    # Firma REAL verificada: TrackerApiError(status, message, *, kind=...).
    # El status es el PRIMER posicional, no el segundo.
    assert list(inspect.signature(TrackerApiError.__init__).parameters)[1] == "status"

    ticket = _TicketFalso(tracker_type="gitlab")
    _preparar(monkeypatch, tmp_path, ticket)
    provider = _ProviderGitLabFalso(explota=TrackerApiError(500, "gitlab dijo que no"))
    _con_provider_gitlab(monkeypatch, provider)

    res = ado_publisher.publish_from_execution(11, triggered_by="test")

    assert res.ok is False and res.status == "failed"
    assert res.error_kind == "tracker_error"
    assert "ADO post_comment failed" not in (res.reason or ""), (
        "un fallo de GitLab no puede reportarse como fallo de ADO"
    )
    assert "gitlab dijo que no" in (res.reason or "")


# ── Caso 6 — el gate se corre CONTRA el defecto ───────────────────────────────


def test_reproduce_el_fallo_de_hoy_con_la_flag_off(monkeypatch, tmp_path):
    """Con STACKY_COMMENT_PUBLISH_ROUTED_ENABLED=False vuelve el bug de hoy.

    No se mockea `build_ado_client`: se fuerza el contexto de proyecto a GitLab y
    el guard REAL de project_context levanta el AdoConfigError con la firma
    literal `no usa Azure DevOps` — la misma que dejo las filas 56 y 57 de
    agent_html_publish en `failed`.
    """
    from services import ado_publisher, project_context

    ticket = _TicketFalso(tracker_type="gitlab")
    _preparar(monkeypatch, tmp_path, ticket)
    monkeypatch.setattr(ado_publisher.config,
                        "STACKY_COMMENT_PUBLISH_ROUTED_ENABLED", False, raising=False)

    class _CtxGitLab:
        tracker_type = "gitlab"
        stacky_project_name = "RIPLEY"

    monkeypatch.setattr(project_context, "require_project_context",
                        lambda *_a, **_k: _CtxGitLab())

    res = ado_publisher.publish_from_execution(11, triggered_by="test")

    assert res.ok is False and res.status == "failed"
    assert "no usa Azure DevOps" in (res.reason or ""), (
        f"el defecto no se reprodujo; reason={res.reason!r}"
    )


# ── Caso 7 — gate de contrato por firma ([A1]) ────────────────────────────────


def test_el_adaptador_acepta_la_llamada_EXACTA_de_ado_publisher():
    """El adaptador se adapta a la llamada de :469, no al reves.

    GUARDA ANTI-FALSO-VERDE: primero se prueba que un objeto con la firma de DOS
    argumentos SI levanta TypeError con tres posicionales. Sin eso, el assert de
    abajo podria pasar porque el detector no detecta nada.
    """
    from services.comment_publish_router import GitLabCommentClient

    provider = _ProviderGitLabFalso()

    # (a) el provider crudo NO acepta la llamada de ado_publisher
    with pytest.raises(TypeError):
        provider.post_comment(1115, "<p>x</p>", "html")

    # (b) el adaptador SI, con los mismos tres posicionales de :469
    adaptador = GitLabCommentClient(provider)
    respuesta = adaptador.post_comment(1115, "<p>x</p>", "html")

    assert isinstance(respuesta, dict)
    assert "id" in respuesta, "ado_publisher exige comment_id en la respuesta"
    assert provider.llamadas == [("1115", "<p>x</p>")], (
        "el adaptador debe pasar el item_id como string y descartar el formato"
    )

    # El contrato tambien se congela por firma: 3 posicionales aceptables.
    firma = inspect.signature(GitLabCommentClient.post_comment)
    firma.bind(adaptador, 1115, "<p>x</p>", "html")   # no levanta
