"""tests/test_plan287_ficha_ticket.py — Plan 287 F1, F1.5 y F2.

El servidor de la ficha del ticket: el historial que ya existia en el puerto y que
nadie habia expuesto, y la matriz de capacidades que dice QUE NO SE PUEDE MOSTRAR
Y POR QUE.

El defecto que este archivo existe para matar (C1 de la critica v1->v2): los dos
adaptadores devuelven formas de `fetch_item_updates` SIN UNA SOLA CLAVE EN COMUN
(ADO: revisedDate/revisedBy/fields · GitLab: kind/created_at/user/label/state/body).
Un normalizador de una sola forma devuelve las 5 claves en None para AMBOS y el
panel nace mudo, en verde. `test_ninguna_fila_sale_toda_en_None` y
`test_paridad_forma_updates_ninguna_fila_muda` son los centinelas que lo atrapan.

Aislamiento (reglas duras de la casa):
  - `DATABASE_URL` a un SQLite de `tmp_path` ANTES de importar `db`/`create_app`:
    un pytest suelto sin eso escribe en la base VIVA del operador.
  - `STACKY_TEST_MODE=1` (lo pone `conftest.py`) => cero egress de red.
  - Nunca se lee un `projects/<X>/config.json` real: el contexto de proyecto se
    inyecta parcheando `resolve_project_context` en el modulo de la ruta.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _cargar_fixtures():
    """Carga el modulo de datos por ruta: `tests/fixtures/` no es un paquete."""
    ruta = Path(__file__).resolve().parent / "fixtures" / "plan287_updates.py"
    spec = importlib.util.spec_from_file_location("plan287_updates", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_FIX = _cargar_fixtures()
UPDATES_ADO = _FIX.UPDATES_ADO
UPDATES_GITLAB = _FIX.UPDATES_GITLAB
UPDATES_POR_TRACKER = _FIX.UPDATES_POR_TRACKER

_CLAVES_DE_LA_FILA = {"fecha", "autor", "campo", "de", "a"}
_CAPACIDAD_HISTORIAL = "tracker.updates.history"


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def bd_aislada(tmp_path, monkeypatch):
    """SQLite temporal. Va ANTES de cualquier import de `db`/`app`."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'plan287.db').as_posix()}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")
    yield


@pytest.fixture()
def app(bd_aislada):
    from app import create_app

    aplicacion = create_app()
    aplicacion.config.update(TESTING=True)
    return aplicacion


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


def _crear_ticket(
    app,
    *,
    ado_id: int = 4321,
    proyecto: str = "RIPLEY",
    tracker_type: str | None = "azure_devops",
) -> int:
    """Crea un ticket y devuelve su id local (el de la URL, no el del tracker)."""
    from db import session_scope
    from models import Ticket

    with app.app_context():
        with session_scope() as s:
            t = Ticket(
                ado_id=ado_id,
                external_id=ado_id,
                project="grupo/proyecto",
                stacky_project_name=proyecto,
                tracker_type=tracker_type,
                title="Ticket de prueba del plan 287",
                work_item_type="Task",
            )
            s.add(t)
            s.flush()
            return t.id


class _ProviderDoble:
    """Doble del puerto. Cuenta llamadas: es lo que prueba el 'no dos veces'."""

    def __init__(self, updates: list[dict] | None = None):
        self.updates = updates if updates is not None else []
        self.llamadas: list[str] = []

    def fetch_item_updates(self, item_id: str, since=None) -> list[dict]:
        self.llamadas.append(str(item_id))
        return list(self.updates)


def _contexto(monkeypatch, tracker: str, nombre: str = "RIPLEY"):
    """Inyecta el contexto de proyecto que la ruta resuelve. Cero disco real."""
    import api.tickets as t
    from services.project_context import ProjectContext

    ctx = ProjectContext(
        stacky_project_name=nombre,
        tracker_type=tracker,
        tracker_project="grupo/proyecto",
    )
    monkeypatch.setattr(t, "resolve_project_context", lambda **_kw: ctx, raising=True)
    return ctx


def _proveedor(monkeypatch, doble: _ProviderDoble) -> list[str]:
    """Reemplaza la COSTURA (get_tracker_provider) y registra por que proyecto se
    pregunto. Si la ruta bifurcara por `ticket.tracker_type` en vez de por la
    costura, esta lista quedaria vacia."""
    import api.tickets as t

    pedidos: list[str] = []

    def _fabrica(project=None, *_a, **_kw):
        pedidos.append(str(project))
        return doble

    monkeypatch.setattr(t, "get_tracker_provider", _fabrica, raising=True)
    return pedidos


# ═════════════════════════════════════════════════════════════════════════════
# F1 — el historial del ticket, por la costura, para los dos trackers (12)
# ═════════════════════════════════════════════════════════════════════════════


def test_historial_devuelve_403_con_la_flag_apagada(app, client, monkeypatch):
    """403 = flag apagada, NUNCA permiso. Mono-operador: no hay roles."""
    import config

    tid = _crear_ticket(app)
    monkeypatch.setattr(config.config, "STACKY_TICKET_HISTORY_API_ENABLED", False, raising=False)

    r = client.get(f"/api/tickets/{tid}/historial")

    assert r.status_code == 403
    assert r.get_json()["error"] == "feature_disabled"


def test_historial_404_si_el_ticket_no_existe(app, client):
    r = client.get("/api/tickets/999999/historial")

    assert r.status_code == 404
    cuerpo = r.get_json()
    assert cuerpo["error"] == "not_found"
    assert "999999" in cuerpo["detalle"]


def test_historial_usa_el_provider_y_no_la_columna_tracker_type(app, client, monkeypatch):
    """EL CASO CENTRAL. Un ticket con la columna diciendo `azure_devops` dentro de
    un proyecto GitLab tiene que consultar al provider de GitLab.

    La columna `tracker_type` es OPCIONAL y MIENTE (planes 281/286): el ruteo va
    por `get_tracker_provider(proyecto)`, que es PROVIDER_SEAM reconocido.
    """
    tid = _crear_ticket(app, tracker_type="azure_devops")   # la columna miente
    _contexto(monkeypatch, "gitlab")                        # el proyecto manda
    doble = _ProviderDoble(UPDATES_GITLAB)
    pedidos = _proveedor(monkeypatch, doble)

    r = client.get(f"/api/tickets/{tid}/historial")

    assert r.status_code == 200
    # PRESENCIA (no solo ausencia): la costura se uso de verdad.
    assert pedidos == ["RIPLEY"], "la ruta no paso por get_tracker_provider(proyecto)"
    assert doble.llamadas, "no se le pregunto al provider"
    # Y el tracker reportado es el del PROYECTO, no el de la columna.
    assert r.get_json()["tracker"] == "gitlab"


def test_historial_devuelve_los_updates_del_provider(app, client, monkeypatch):
    """Pasa por el puerto y normaliza. Las fixtures son las formas REALES."""
    tid = _crear_ticket(app)
    _contexto(monkeypatch, "azure_devops")
    doble = _ProviderDoble(UPDATES_ADO[:2])
    _proveedor(monkeypatch, doble)

    r = client.get(f"/api/tickets/{tid}/historial")

    assert r.status_code == 200
    historial = r.get_json()["historial"]
    assert len(historial) == 2
    assert historial[0]["campo"] == "Estado"
    assert historial[0]["de"] == "New" and historial[0]["a"] == "Active"


def test_historial_degrada_sin_romper_si_la_capacidad_esta_ausente(app, client, monkeypatch):
    """Capacidad `absent` => 200 con lista vacia y el motivo escrito. NUNCA 500."""
    import api.tickets as t

    tid = _crear_ticket(app)
    _contexto(monkeypatch, "gitlab")
    monkeypatch.setattr(t, "capability_status", lambda *_a, **_k: "absent", raising=True)
    monkeypatch.setattr(t, "supports", lambda *_a, **_k: False, raising=True)
    doble = _ProviderDoble(UPDATES_GITLAB)
    _proveedor(monkeypatch, doble)

    r = client.get(f"/api/tickets/{tid}/historial")

    assert r.status_code == 200
    cuerpo = r.get_json()
    assert cuerpo["historial"] == []
    assert cuerpo["capacidad"]["estado"] == "absent"
    # Y no se molesto al tracker por algo que declaro no soportar.
    assert doble.llamadas == []


def test_historial_informa_la_perdida_cuando_la_capacidad_es_parcial(app, client, monkeypatch):
    """En GitLab la capacidad es `partial` con perdida escrita: tiene que viajar."""
    tid = _crear_ticket(app)
    _contexto(monkeypatch, "gitlab")
    _proveedor(monkeypatch, _ProviderDoble(UPDATES_GITLAB))

    r = client.get(f"/api/tickets/{tid}/historial")

    cap = r.get_json()["capacidad"]
    assert cap["clave"] == _CAPACIDAD_HISTORIAL
    assert cap["estado"] == "partial"
    assert cap["perdida"].strip(), "la perdida declarada llego vacia"


def test_historial_503_si_el_tracker_no_esta_configurado(app, client, monkeypatch):
    """TrackerConfigError => 503 tipado, no una traza cruda ni un 500."""
    import api.tickets as t
    from services.tracker_provider import TrackerConfigError

    tid = _crear_ticket(app)
    _contexto(monkeypatch, "gitlab")

    def _explota(*_a, **_kw):
        raise TrackerConfigError("GitLab no esta configurado en este proyecto")

    monkeypatch.setattr(t, "get_tracker_provider", _explota, raising=True)

    r = client.get(f"/api/tickets/{tid}/historial")

    assert r.status_code == 503
    cuerpo = r.get_json()
    assert cuerpo["error"] == "tracker_no_configurado"
    assert "GitLab" in cuerpo["detalle"]


def test_historial_no_llama_al_tracker_dos_veces(app, client, monkeypatch):
    tid = _crear_ticket(app)
    _contexto(monkeypatch, "azure_devops")
    doble = _ProviderDoble(UPDATES_ADO)
    _proveedor(monkeypatch, doble)

    client.get(f"/api/tickets/{tid}/historial")

    assert len(doble.llamadas) == 1


def test_normaliza_la_forma_REAL_de_ado():
    """v2/C1 — la forma que devuelve services/ado_provider.py:137 (el `value` crudo)."""
    from api.tickets import _normalizar_update

    u = {
        "rev": 2,
        "revisedDate": "2026-06-01T10:00:00Z",
        "revisedBy": {"displayName": "Ana Perez"},
        "fields": {"System.State": {"oldValue": "New", "newValue": "Active"}},
    }

    filas = _normalizar_update(u, "azure_devops")

    assert len(filas) == 1
    f = filas[0]
    assert f["fecha"] == "2026-06-01T10:00:00Z"
    assert f["autor"] == "Ana Perez"
    assert f["campo"] == "Estado"
    assert f["de"] == "New"
    assert f["a"] == "Active"


def test_normaliza_la_forma_REAL_de_gitlab():
    """v2/C1 — la forma que ARMA services/gitlab_provider.py:606-666.

    Ojo: `user` YA es el username (string), lo extrae el adaptador en :622.
    """
    from api.tickets import _normalizar_update

    estado = _normalizar_update(UPDATES_GITLAB[0], "gitlab")
    etiqueta = _normalizar_update(UPDATES_GITLAB[1], "gitlab")

    assert len(estado) == 1 and len(etiqueta) == 1
    assert estado[0]["autor"] == "dev" and etiqueta[0]["autor"] == "dev"
    assert estado[0]["fecha"] and etiqueta[0]["fecha"]
    assert {estado[0]["campo"], etiqueta[0]["campo"]} == {"Estado", "Etiqueta"}
    assert estado[0]["a"] == "closed"
    assert etiqueta[0]["a"] == "bug"      # action == "add" => entra en "a"


@pytest.mark.parametrize("tracker", sorted(UPDATES_POR_TRACKER))
def test_ninguna_fila_sale_toda_en_None(tracker):
    """v2/C1 — EL CENTINELA ANTI-PANEL-MUDO.

    Con la implementacion ingenua de la v1 (`u.get("fecha")`, `u.get("autor")`, …)
    este test FALLA en los DOS trackers: la interseccion de claves es vacia.
    """
    from api.tickets import _normalizar_update

    total = 0
    for u in UPDATES_POR_TRACKER[tracker]:
        for fila in _normalizar_update(u, tracker):
            total += 1
            assert any(fila[k] is not None for k in _CLAVES_DE_LA_FILA), (
                f"fila MUDA en {tracker}: {fila} (origen {u})"
            )
    assert total > 0, f"{tracker} no produjo ni una fila: el mapeo no se aplico"


def test_normalizador_no_lanza_ante_basura():
    """NUNCA lanza: la ficha degrada, no rompe."""
    from api.tickets import _normalizar_update

    for tracker in ("azure_devops", "gitlab"):
        for basura in ({}, {"kind": "inventado"}, {"fields": "no es dict"},
                       {"fields": {"System.State": "no es dict"}}, {"revisedBy": None}):
            salida = _normalizar_update(basura, tracker)
            assert isinstance(salida, list)


# ═════════════════════════════════════════════════════════════════════════════
# F1.5 — el centinela de forma del puerto (3)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("tracker", sorted(UPDATES_POR_TRACKER))
def test_paridad_forma_updates_las_cinco_claves(tracker):
    """La fila normalizada tiene EXACTAMENTE las 5 claves. Congela el contrato."""
    from api.tickets import _normalizar_update

    vistas = 0
    for u in UPDATES_POR_TRACKER[tracker]:
        for fila in _normalizar_update(u, tracker):
            vistas += 1
            assert set(fila.keys()) == _CLAVES_DE_LA_FILA
            for v in fila.values():
                assert v is None or isinstance(v, str), f"valor no serializable: {v!r}"
    assert vistas > 0


@pytest.mark.parametrize("tracker", sorted(UPDATES_POR_TRACKER))
def test_paridad_forma_updates_ninguna_fila_muda(tracker):
    """ESTE es el test que habria matado a C1 en la v1.

    Para CADA fixture de CADA tracker, al menos una de las 5 claves no es None.
    """
    from api.tickets import _normalizar_update

    for u in UPDATES_POR_TRACKER[tracker]:
        filas = _normalizar_update(u, tracker)
        assert filas, f"{tracker}: la entrada {u} no produjo ni una fila"
        for fila in filas:
            assert any(fila[k] is not None for k in _CLAVES_DE_LA_FILA), (
                f"PANEL MUDO en {tracker}: {fila}"
            )


def test_paridad_forma_updates_el_fixture_refleja_al_adaptador():
    """Deja escrito cual era la forma esperada de cada adaptador."""
    assert {"kind", "created_at", "user"} <= set(UPDATES_GITLAB[0].keys())
    assert {"revisedDate", "revisedBy", "fields"} <= set(UPDATES_ADO[0].keys())
    # Y la asimetria que hace inevitable el mapeo por tracker:
    assert not (set(UPDATES_ADO[0]) & set(UPDATES_GITLAB[0])), (
        "si los dos adaptadores comparten una clave, revisar el mapeo de F1"
    )


# ═════════════════════════════════════════════════════════════════════════════
# F2 — la matriz de capacidades, publicada (6)
# ═════════════════════════════════════════════════════════════════════════════


def test_capacidades_403_con_la_flag_apagada(app, client, monkeypatch):
    import config

    monkeypatch.setattr(
        config.config, "STACKY_TRACKER_CAPABILITIES_API_ENABLED", False, raising=False
    )

    r = client.get("/api/tickets/capacidades")

    assert r.status_code == 403
    assert r.get_json()["error"] == "feature_disabled"


def test_capacidades_devuelve_las_cuatro_claves_de_la_ficha(app, client, monkeypatch):
    """Exactamente 4 claves: publicar de mas es superficie inutil."""
    from api.tickets import _CAPACIDADES_DE_LA_FICHA

    _contexto(monkeypatch, "gitlab")

    r = client.get("/api/tickets/capacidades")

    assert r.status_code == 200
    caps = r.get_json()["capacidades"]
    assert set(caps.keys()) == set(_CAPACIDADES_DE_LA_FICHA)
    assert len(caps) == 4


def test_capacidades_de_gitlab_traen_la_perdida_escrita(app, client, monkeypatch):
    _contexto(monkeypatch, "gitlab")

    r = client.get("/api/tickets/capacidades")

    cuerpo = r.get_json()
    assert cuerpo["tracker"] == "gitlab"
    adjuntos = cuerpo["capacidades"]["tracker.attachments.list"]
    assert adjuntos["estado"] == "partial"
    assert adjuntos["perdida"].strip()


def test_capacidades_de_ado_marcan_full_donde_corresponde(app, client, monkeypatch):
    _contexto(monkeypatch, "azure_devops")

    r = client.get("/api/tickets/capacidades")

    comentarios = r.get_json()["capacidades"]["tracker.comments.list"]
    assert comentarios["estado"] == "full"
    assert comentarios["perdida"] == ""


def test_la_perdida_de_historial_de_gitlab_dice_la_verdad(app, client, monkeypatch):
    """v2/C9 — el texto de hoy MIENTE y corre CONTRA el defecto.

    `fetch_item_updates` (gitlab_provider.py:606) SI consulta resource_label_events
    (:613) y resource_state_events (:630). Lo silenciado son los ERRORES de esas
    sub-consultas (`except Exception: pass` en :625, :641, :656), no las consultas.
    El anclaje viejo (:413) es el armado de etiquetas de `update_item_state`.
    """
    _contexto(monkeypatch, "gitlab")

    r = client.get("/api/tickets/capacidades")

    texto = r.get_json()["capacidades"]["tracker.updates.history"]["perdida"]
    assert "except mudo" in texto
    assert "silenciadas" not in texto
    assert "sin historial de estado" not in texto


# ── Los 2 centinelas HEREDADOS (C7: pasaban ANTES del cambio, fuera del conteo
#    de aceptacion de la fase, pero se conservan) ───────────────────────────────


def test_capacidades_no_importa_nada_de_api_desde_services():
    """Guardarrail estructural: `services/` no importa de `api/`."""
    import ast

    ruta = _BACKEND / "services" / "provider_capabilities.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").startswith("api"):
            pytest.fail(f"services/ importa de api/: {nodo.module}")
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                assert not alias.name.startswith("api."), f"services/ importa {alias.name}"


def test_capacidades_lo_desconocido_es_absent_no_explota():
    from services.provider_capabilities import capability_status, supports

    assert capability_status("gitlab", "tracker.inventada.total") == "absent"
    assert supports("gitlab", "tracker.inventada.total") is False
    assert capability_status("tracker_que_no_existe", "tracker.comments.list") == "absent"
