"""Plan 271 — dobles compartidos. Sin red, sin ADO real, sin GitLab real."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeProvider:
    """Doble de TrackerProvider. Registra escrituras; get_item devuelve el estado
    que le sembrés (o {} para simular 'no se pudo leer')."""

    def __init__(self, current_state: str | None = None):
        self.current_state = current_state
        self.writes: list[tuple[str, str]] = []

    def get_item(self, item_id: str) -> dict:
        return {"state": self.current_state} if self.current_state else {}

    def update_item_state(self, item_id: str, logical_state: str) -> dict:
        self.writes.append((str(item_id), logical_state))
        return {"ok": True}


class _FakeTicket:
    def __init__(self, ado_id, project, work_item_type):
        self.ado_id = ado_id
        self.stacky_project_name = project
        self.work_item_type = work_item_type


class _FakeSession:
    def __init__(self, ticket):
        self._t = ticket

    def get(self, _model, _pk):
        return self._t


def patch_motor_a(monkeypatch, *, profile: dict, ado_id=4242, project="P271",
                  work_item_type=None, provider: FakeProvider | None = None):
    """Parchea TODO lo que `completion_state.maybe_apply_state_transition` importa
    DENTRO de la función. Ojo: son imports locales, así que hay que parchear el
    MÓDULO ORIGEN, no `completion_state`.

    Parchea exactamente:
      - db.session_scope                                   (completion_state.py:56)
      - services.client_profile.load_effective_client_profile   (:85)
      - services.tracker_provider.get_tracker_provider          (:101)
      - services.completion_dispatcher.emit_completion_log      (:171)  -> no-op
    Devuelve el FakeProvider usado (para inspeccionar `.writes`).
    """
    import contextlib
    import db as _db
    import services.client_profile as _cp
    import services.completion_dispatcher as _cd
    import services.tracker_provider as _tp

    prov = provider if provider is not None else FakeProvider()
    ticket = _FakeTicket(ado_id, project, work_item_type)

    @contextlib.contextmanager
    def _scope(*_a, **_k):
        yield _FakeSession(ticket)

    monkeypatch.setattr(_db, "session_scope", _scope)
    monkeypatch.setattr(_cp, "load_effective_client_profile", lambda *_a, **_k: profile)
    monkeypatch.setattr(_tp, "get_tracker_provider", lambda *_a, **_k: prov)
    monkeypatch.setattr(_cd, "emit_completion_log", lambda **_k: None)
    return prov


def close_sin_html(monkeypatch, *, transition_state: str = "To Do"):
    """Llama close_execution_with_publish con html_output_path=None y
    final_status='completed', con la execution+ticket ya sembrados por el caller.

    `agent_completion_internal` resuelve sus helpers POR ATRIBUTO DE MÓDULO, así
    que acá sí se parchea el propio módulo (al revés que en patch_motor_a).
    Modelalo sobre `backend/tests/test_u2_publish_review_mode.py:150-162`, que ya
    siembra la execution con el mismo patrón. Devuelve el CloseResult.
    """
    import services.agent_completion_internal as aci
    import services.tracker_write_router as _twr

    monkeypatch.setattr(aci, "_resolve_transition_state_from_config",
                        lambda **_k: transition_state)
    # F3 rutea por resolve_state_writer(ticket); "P271" no es un proyecto real
    # configurado en disco, así que se parchea el resolver con un doble
    # ado_client que SIEMPRE escribe ok (aísla el test de RC-2/publish del
    # ruteo ADO/GitLab, que tiene su propia batería en test_plan271_writer_routed.py).
    monkeypatch.setattr(
        _twr, "resolve_state_writer",
        lambda _ticket: _twr.StateWriter(tracker_type="azure_devops", kind="provider",
                                          handle=FakeProvider()),
    )
    execution_id, _ticket_id = _seed_execution_y_ticket()
    return aci.close_execution_with_publish(
        execution_id=execution_id, triggered_by="test_plan271",
        final_status="completed", html_output_path=None,
    )


def _seed_execution_y_ticket() -> tuple[int, int]:
    """Siembra un Ticket (con `stacky_project_name` seteado — sin él, F3 cae al
    camino legacy, ver D6) y una AgentExecution 'running'. Devuelve (exec, ticket).
    Copiá el patrón exacto de `test_u2_publish_review_mode.py:150-162`; lo único
    que NO se puede omitir es `stacky_project_name`."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=4242, project="P271", stacky_project_name="P271",
                   title="t-271", ado_state="New", stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="technical", status="running",
                           input_context_json="[]", started_by="test")
        s.add(e)
        s.flush()
        return e.id, t.id
