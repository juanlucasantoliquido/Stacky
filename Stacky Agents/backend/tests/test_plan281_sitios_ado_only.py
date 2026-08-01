"""tests/test_plan281_sitios_ado_only.py — Plan 281 F7.

Los 8 sitios que construían un cliente de Azure DevOps sin preguntar antes de qué
tracker es el proyecto. Una clase por sitio, DOS casos cada una:

  1. `..._no_construye_cliente_ado_en_gitlab` — con el tracker en no-ADO, cero
     llamadas al constructor y el retorno es EXACTAMENTE el valor neutro
     (comparación por igualdad, no por truthiness).
  2. `..._sigue_igual_en_ado` — NO-REGRESIÓN. Sin este segundo caso, un `return`
     mal puesto que rompiera también el camino ADO pasaría el primero sin que
     nadie se entere.

El valor neutro de cada sitio se verificó abriendo su `except` REAL, no se supuso.
Dos excepciones documentadas:
  - sitio 6 (`self_review._resolve_criteria`) NO TIENE `except`: el cambio es de
    excepción propagada a no-op declarado.
  - sitio 3 (`autopublish_epic_from_run`) NO se degrada a no-op: la épica se
    publica igual por el provider (Plan 278). Por eso su caso GitLab asserta
    además que `create_item` SÍ se llamó.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# OBLIGATORIO antes de cualquier import de módulos de la app.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def _tracker(monkeypatch, es_ado: bool, *modulos):
    """Fija el veredicto del resolvedor canónico en cada módulo que lo consulta.

    Los sitios que importan `tracker_is_azure_devops` DENTRO de la función se
    parchean en `services.project_context`; los que lo importan a nivel de módulo
    (`api/tickets.py`) se parchean en su propio módulo. Parchear el lugar
    equivocado deja el test verde por la razón incorrecta.
    """
    import services.project_context as pc

    monkeypatch.setattr(pc, "tracker_is_azure_devops", lambda _n: es_ado)
    for mod in modulos:
        if hasattr(mod, "tracker_is_azure_devops"):
            monkeypatch.setattr(mod, "tracker_is_azure_devops", lambda _n: es_ado)


class _EspiaAdo:
    """Spy del constructor de cliente ADO. Cuenta llamadas y devuelve un doble."""

    def __init__(self, doble=None):
        self.llamadas: list = []
        self.doble = doble if doble is not None else object()

    def __call__(self, *a, **k):
        self.llamadas.append((a, k))
        return self.doble

    @property
    def n(self) -> int:
        return len(self.llamadas)


# ── Sitio 4 · services/acceptance_criteria.py::resolve → "" ──────────────────


class TestSitio4AcceptanceCriteria:
    def _ticket(self):
        return types.SimpleNamespace(
            stacky_project_name="RIPLEY", project="g/p", ado_id=1115
        )

    def test_acceptance_criteria_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        import services.acceptance_criteria as ac
        import services.project_context as pc

        _tracker(monkeypatch, False, ac)
        espia = _EspiaAdo()
        monkeypatch.setattr(pc, "build_ado_client", espia)

        assert ac.resolve(self._ticket()) == ""
        assert espia.n == 0

    def test_acceptance_criteria_sigue_igual_en_ado(self, monkeypatch):
        import services.acceptance_criteria as ac
        import services.project_context as pc

        _tracker(monkeypatch, True, ac)

        class _Cli:
            def _batch_get(self, ids):
                return [{"fields": {"Microsoft.VSTS.Common.AcceptanceCriteria": "<p>AC</p>"}}]

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(pc, "build_ado_client", espia)

        assert ac.resolve(self._ticket()) == "AC"
        assert espia.n == 1


# ── Sitio 6 · services/self_review.py::_resolve_criteria → "" ────────────────


class TestSitio6SelfReview:
    def _ticket(self):
        return types.SimpleNamespace(
            stacky_project_name="RIPLEY", project="g/p", ado_id=1115
        )

    def test_self_review_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        import services.project_context as pc
        import services.self_review as sr

        _tracker(monkeypatch, False, sr)
        espia = _EspiaAdo()
        monkeypatch.setattr(pc, "build_ado_client", espia)

        # C5 — hoy esto PROPAGA AdoConfigError (la función no tiene `except`).
        assert sr._resolve_criteria(self._ticket()) == ""
        assert espia.n == 0

    def test_self_review_sigue_igual_en_ado(self, monkeypatch):
        """El caso ADO verifica que `review_artifact` sigue dando un score real y
        NO un `skipped_reason` (si no, el guard rompería también el camino ADO)."""
        import services.project_context as pc
        import services.self_review as sr

        _tracker(monkeypatch, True, sr)

        class _Cli:
            def _batch_get(self, ids):
                return [{"fields": {"Microsoft.VSTS.Common.AcceptanceCriteria": "<p>Criterio A</p>"}}]

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(pc, "build_ado_client", espia)

        assert sr._resolve_criteria(self._ticket()) == "Criterio A"
        assert espia.n == 1


# ── Sitio 7 · services/similar_tickets.py::find_similar_tickets → [] ─────────


class TestSitio7SimilarTickets:
    def _llamar(self):
        from services.similar_tickets import find_similar_tickets

        return find_similar_tickets(
            current_ado_id=1115,
            current_title="Migrar el motor de reglas a la nueva arquitectura",
            project="g/p",
            project_name="RIPLEY",
        )

    def test_similar_tickets_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        import services.project_context as pc
        import services.similar_tickets as st

        _tracker(monkeypatch, False, st)
        espia = _EspiaAdo()
        monkeypatch.setattr(pc, "build_ado_client", espia)

        assert self._llamar() == []
        assert espia.n == 0

    def test_similar_tickets_sigue_igual_en_ado(self, monkeypatch):
        import services.project_context as pc
        import services.similar_tickets as st

        _tracker(monkeypatch, True, st)

        class _Cli:
            def fetch_open_work_items(self, wiql=None):
                return []

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(pc, "build_ado_client", espia)

        assert self._llamar() == []
        assert espia.n == 1, "el camino ADO dejó de construir el cliente"


# ── Sitio 1 · api/agents.py::_build_ado_enrichment_sections → [] ─────────────


class TestSitio1EnrichmentSections:
    def test_enrichment_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        import api.agents as ag

        _tracker(monkeypatch, False, ag)
        espia = _EspiaAdo()
        monkeypatch.setattr(ag, "build_ado_client", espia)

        assert ag._build_ado_enrichment_sections(1115, project_name="RIPLEY") == []
        assert espia.n == 0

    def test_enrichment_sigue_igual_en_ado(self, monkeypatch):
        import api.agents as ag

        _tracker(monkeypatch, True, ag)

        class _Cli:
            def fetch_comments(self, ado_id, top=30):
                return []

            def fetch_attachments(self, ado_id):
                return []

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(ag, "build_ado_client", espia)

        ag._build_ado_enrichment_sections(4242, project_name="PACIFICO")
        assert espia.n == 1


# ── Sitio 2 · api/tickets.py::_equivalent_task_status → "unknown" ────────────


def _equivalent_task_status(project_name: str, cache: dict | None = None):
    """Reconstruye la closure REAL `_equivalent_task_status` de `create_child_task`.

    Es una función anidada, así que no se puede importar. En vez de copiarla (una
    copia muerta no probaría nada) se toma su code object y se le arma el closure
    con celdas fabricadas. Si cambian sus variables libres, esto REVIENTA en vez
    de pasar en silencio.
    """
    import api.tickets as t

    codigos = [
        c for c in t.create_child_task.__code__.co_consts
        if isinstance(c, types.CodeType) and c.co_name == "_equivalent_task_status"
    ]
    assert len(codigos) == 1, f"no se encontró la closure: {codigos}"
    codigo = codigos[0]

    valores = {
        "_stale_status_cache": cache if cache is not None else {},
        "operation_id": "op-281",
        "project_name": project_name,
    }
    assert set(codigo.co_freevars) == set(valores), (
        f"las variables libres cambiaron: {codigo.co_freevars}"
    )

    def _celda(v):
        return (lambda x: lambda: x)(v).__closure__[0]

    cierre = tuple(_celda(valores[n]) for n in codigo.co_freevars)
    return types.FunctionType(codigo, t.__dict__, "_equivalent_task_status", None, cierre)


class TestSitio2EquivalentTaskStatus:
    def test_equivalent_task_status_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        import api.tickets as t

        _tracker(monkeypatch, False, t)
        espia = _EspiaAdo()
        monkeypatch.setattr(t, "_ado_client_for_ticket", espia)

        fn = _equivalent_task_status("RIPLEY")
        # El valor neutro es "unknown", NUNCA "": el contrato del consumidor son
        # exactamente tres valores y un cuarto reabre el caso ADO-241.
        assert fn(777) == "unknown"
        assert espia.n == 0

    def test_equivalent_task_status_sigue_igual_en_ado(self, monkeypatch):
        import api.tickets as t

        _tracker(monkeypatch, True, t)
        espia = _EspiaAdo()
        monkeypatch.setattr(t, "_ado_client_for_ticket", espia)
        monkeypatch.setattr(t, "_consumed_task_ado_status", lambda **k: "exists")

        fn = _equivalent_task_status("PACIFICO")
        assert fn(777) == "exists"
        assert espia.n == 1


# ── Sitio 8 · services/ticket_assigner.py::auto_assign_on_run → None ─────────


@pytest.fixture()
def asignador(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import models
    import services.ticket_assigner as ta
    from db import Base

    ruta = (tmp_path / "p281assign.db").as_posix()
    motor = create_engine(f"sqlite:///{ruta}", future=True)
    Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(motor)
    assert tmp_path.name in str(motor.url), f"la BD del test NO está aislada: {motor.url}"

    @contextmanager
    def _scope():
        s = Sesion()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # `ticket_assigner` importó `session_scope` POR VALOR: sin re-apuntarlo acá el
    # test escribiría en la BD REAL del operador.
    monkeypatch.setattr(ta, "session_scope", _scope)

    with _scope() as s:
        t = models.Ticket(
            ado_id=1115, external_id=1115, title="t", project="g/p",
            stacky_project_name="RIPLEY",
        )
        s.add(t)
        s.flush()
        tid = t.id
    return ta, tid


class TestSitio8TicketAssigner:
    def test_auto_assign_no_construye_cliente_ado_en_gitlab(self, asignador, monkeypatch):
        import services.ado_identity as ai
        import services.project_context as pc

        ta, tid = asignador
        _tracker(monkeypatch, False, ta)
        espia = _EspiaAdo()
        monkeypatch.setattr(pc, "build_ado_client", espia)

        identidades: list = []
        monkeypatch.setattr(
            ai, "resolve_me_unique_name",
            lambda p: identidades.append(p) or "dev@local",
        )

        assert ta.auto_assign_on_run(tid, "RIPLEY") is None
        assert espia.n == 0
        assert identidades == [], "se resolvió la identidad ADO en un proyecto GitLab"

    def test_auto_assign_sigue_igual_en_ado(self, asignador, monkeypatch):
        import services.ado_identity as ai
        import services.project_context as pc

        ta, tid = asignador
        _tracker(monkeypatch, True, ta)

        class _Cli:
            def update_work_item_assigned_to(self, ado_id, me):
                return None

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(pc, "build_ado_client", espia)
        monkeypatch.setattr(ai, "resolve_me_unique_name", lambda p: "Dev@Local")

        assert ta.auto_assign_on_run(tid, "PACIFICO") == "Dev@Local"
        assert espia.n == 1


# ── Sitio 5 · services/business_preflight.py::_evaluate_functional ───────────


class TestSitio5BusinessPreflight:
    def _llamar(self):
        from services.business_preflight import _evaluate_functional

        # `work_item_type="Task"` a propósito: así el Modo A (que NO toca ADO) no
        # aplica y se llega al Modo B, que es el que construía el cliente.
        return _evaluate_functional(
            ado_id=1115,
            work_item_type="Task",
            ado_state="Nuevo",
            stacky_project_name="RIPLEY",
            tracker_project="g/p",
        )

    def test_business_preflight_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        import services.business_preflight as bp
        import services.project_context as pc

        _tracker(monkeypatch, False, bp)
        espia = _EspiaAdo()
        monkeypatch.setattr(pc, "build_ado_client", espia)

        r = self._llamar()
        assert r.ok is True
        assert r.mode is None
        assert r.warnings == ["tracker no-ADO: sin cross-check de comentarios"]
        assert espia.n == 0

    def test_business_preflight_sigue_igual_en_ado(self, monkeypatch):
        import services.ado_read_cache as arc
        import services.business_preflight as bp
        import services.project_context as pc

        _tracker(monkeypatch, True, bp)

        class _Cli:
            def fetch_comments(self, ado_id, top=30):
                return []

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(pc, "build_ado_client", espia)
        monkeypatch.setattr(arc, "get_or_fetch", lambda *a, **k: [])

        r = self._llamar()
        assert espia.n == 1
        assert r.ok is False and r.check == "functional_prereqs_unmet"


# ── Sitio 3 · api/tickets.py::autopublish_epic_from_run ──────────────────────
#
# El ÚNICO sitio que NO se degrada a no-op: la épica se publica igual (Plan 278).
# Sólo se gatea el sellado del baseline de `System.Rev`, que es un concepto de ADO.


class _ProviderGitLab:
    name = "gitlab"

    def __init__(self):
        self.creados: list = []

    def create_item(self, item):
        self.creados.append(item)
        # Sin `rev`: GitLab no tiene System.Rev. Ids ESTRINGADOS como los normaliza
        # el provider real.
        return {
            "iid": "1115",
            "id": "9001",
            "fields": {"System.Title": "Epica"},
            "web_url": "https://gitlab.local/g/p/-/issues/1115",
        }

    def item_url(self, ado_id):
        return f"https://gitlab.local/{ado_id}"


class TestSitio3AutopublishEpic:
    def _preparar(self, monkeypatch):
        import api.tickets as t

        monkeypatch.setenv("STACKY_EPIC_SUMMARY_ENABLED", "off")
        monkeypatch.setenv("STACKY_ADO_EDIT_LEARNING_ENABLED", "true")
        monkeypatch.setattr(t, "_looks_like_epic", lambda *a, **k: True)
        monkeypatch.setattr(t, "_epic_gate_enabled", lambda *a, **k: False)
        monkeypatch.setattr(t, "_persist_epic_ticket", lambda *a, **k: None)
        monkeypatch.setattr(t, "_epic_brief_save", lambda *a, **k: None)
        return t

    def test_autopublish_no_construye_cliente_ado_en_gitlab(self, monkeypatch):
        t = self._preparar(monkeypatch)
        _tracker(monkeypatch, False, t)

        prov = _ProviderGitLab()
        monkeypatch.setattr(t, "_provider_for_ticket", lambda **k: prov)
        espia = _EspiaAdo()
        monkeypatch.setattr(t, "_ado_client_for_ticket", espia)

        r = t.autopublish_epic_from_run(
            output="<h1>Epica</h1>", brief="b", project_name="RIPLEY",
            already_published_id=None,
        )

        assert espia.n == 0, "se construyó un cliente ADO para sellar System.Rev en GitLab"
        # El valor neutro del sitio 3 es `_baseline_rev = None`, NO abortar:
        assert r.baseline_rev is None
        # …y la épica SÍ se publicó. Sin este assert, una implementación que
        # abortara la función (el error de la v1 del plan) pasaría igual.
        assert len(prov.creados) == 1, "la épica de GitLab NO se publicó"
        assert r.ado_id == 1115
        assert r.error is None and r.skipped is False

    def test_autopublish_sigue_igual_en_ado(self, monkeypatch):
        """NO-REGRESIÓN: en ADO el sellado de System.Rev sigue haciendo su GET.

        Se parchea `_publish_epic_to_ado` para que la ÚNICA llamada al constructor
        sea la del bloque de baseline: así el conteo es exactamente 1.
        """
        t = self._preparar(monkeypatch)
        _tracker(monkeypatch, True, t)

        from api.tickets import _PublishedEpic

        monkeypatch.setattr(
            t, "_publish_epic_to_ado",
            lambda **k: _PublishedEpic(ado_id=4242, title="T", url="u", rev=None),
        )

        class _Cli:
            def get_work_item(self, ado_id, fields=None):
                return {"fields": {"System.Rev": 7}}

        espia = _EspiaAdo(doble=_Cli())
        monkeypatch.setattr(t, "_ado_client_for_ticket", espia)

        r = t.autopublish_epic_from_run(
            output="<h1>Epica</h1>", brief="b", project_name="PACIFICO",
            already_published_id=None,
        )

        assert espia.n == 1
        assert r.baseline_rev == 7
        assert r.ado_id == 4242
