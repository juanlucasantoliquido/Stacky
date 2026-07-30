"""tests/test_mg_states.py — pasada de aplicación de ESTADO (cerrar/reabrir).

Cubre `tools/migrar_mantis_gitlab/migrator_mg_states.py`, que es el paso que
faltaba para que el `gitlab_state` de `field_mapping.status` llegue realmente a
GitLab. El bug que estos tests blindan (medido contra Ripley, proyecto GitLab
127): 52 issues migradas, 52 abiertas, 0 cerradas, con una etiquetada
`status::resolved`.

Qué se valida:
  (a) `resolved`/`closed` de Mantis producen un cierre; los estados abiertos no.
  (b) Idempotencia real: si el destino ya está en el estado deseado, NO se emite
      ninguna escritura (ni un PUT de más).
  (c) Simetría: un ticket reabierto en Mantis reabre el issue en GitLab.
  (d) Un status sin mapeo explícito cae a `_unmapped_fallback` y se DECLARA.
  (e) Un ticket del origen que todavía no está migrado no es un error: se
      reporta en `not_migrated` y no se toca.
  (f) Un fallo al aplicar un estado no aborta la pasada.
  (g) La nota de trazabilidad de `closed_at` se agrega una sola vez.
  (h) `desired_state` inválido en el config se declara y no emite escritura.
  (i) `fetch_destination_states` incluye los issues CERRADOS (si sólo viera los
      abiertos, la pasada re-cerraría en cada corrida y no vería reaperturas).
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab.destination_writer import DestinationWriter
from tools.migrar_mantis_gitlab.migrator_mg_states import (
    apply_state_changes,
    fetch_destination_states,
    plan_state_changes,
)

_MANTIS_PROJECT_ID = "310"

# Mismo bloque que `deployment/migration_config_ripley.json` §field_mapping.status
_STATUS_CFG = {
    "new": {"gitlab_state": "opened", "label": "status::new"},
    "feedback": {"gitlab_state": "opened", "label": "status::feedback"},
    "acknowledged": {"gitlab_state": "opened", "label": "status::acknowledged"},
    "confirmed": {"gitlab_state": "opened", "label": "status::confirmed"},
    "assigned": {"gitlab_state": "opened", "label": "status::assigned"},
    "resolved": {"gitlab_state": "closed", "label": "status::resolved"},
    "closed": {"gitlab_state": "closed", "label": "status::closed"},
    "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
}


class _StateWriter(DestinationWriter):
    """Fake que registra cada escritura, para poder afirmar que NO se escribió
    cuando no correspondía (la afirmación central de la idempotencia)."""

    def __init__(self, *, items: "list[dict] | None" = None, fail_iids: "set[str] | None" = None) -> None:
        self._items = items or []
        self._fail_iids = fail_iids or set()
        self.state_calls: list[tuple[str, str]] = []
        self.updated_at_calls: list = []
        self.comments: list[tuple[str, str]] = []
        self.comment_dates: list = []

    def create_item(self, payload):
        raise AssertionError("la pasada de estados no debe crear issues")

    def post_comment(self, item_iid, body, created_at=None):
        self.comments.append((str(item_iid), body))
        self.comment_dates.append(created_at)
        return {"id": f"note-{len(self.comments)}"}

    def upload_attachment(self, file_path, filename):
        raise AssertionError("la pasada de estados no debe subir adjuntos")

    def link_attachment(self, item_iid, attachment_meta):
        raise AssertionError("la pasada de estados no debe enlazar adjuntos")

    def create_issue_link(self, source_iid, target_iid, link_type):
        raise AssertionError("la pasada de estados no debe crear links")

    def ensure_milestone(self, title):
        raise AssertionError("la pasada de estados no debe crear milestones")

    def apply_item_state(self, item_iid, desired_state, updated_at=None):
        if str(item_iid) in self._fail_iids:
            raise RuntimeError(f"fallo simulado en issue {item_iid}")
        self.state_calls.append((str(item_iid), desired_state))
        self.updated_at_calls.append(updated_at)
        return {"iid": str(item_iid), "state": desired_state}

    def fetch_states(self):
        return []

    def fetch_open_items(self):
        return self._items

    def comment_exists(self, item_iid, marker):
        return any(iid == str(item_iid) and marker in body for iid, body in self.comments)

    def effective_target(self):
        return ("https://fake.local", "grupo/repo-demo")


# ── (a) resolved/closed cierran; los abiertos no ────────────────────────────


def test_resolved_y_closed_cierran_y_los_abiertos_no():
    origin = [
        {"id": 101, "status": "resolved"},
        {"id": 102, "status": "closed"},
        {"id": 103, "status": "confirmed"},
        {"id": 104, "status": "feedback"},
    ]
    mapping = {"101": "1", "102": "2", "103": "3", "104": "4"}
    destino = {"1": "opened", "2": "opened", "3": "opened", "4": "opened"}

    result = plan_state_changes(origin, _STATUS_CFG, mapping, destino)

    assert result.to_close == 2
    assert result.to_reopen == 0
    # Los 2 abiertos ya estaban bien: no generan cambio.
    assert result.already_ok == 2
    assert {c.mantis_issue_id for c in result.changes} == {"101", "102"}
    assert all(c.action == "close" for c in result.changes)


# ── (b) idempotencia: nada que hacer => CERO escrituras ─────────────────────


def test_idempotencia_no_emite_ninguna_escritura_si_el_destino_ya_esta_bien():
    origin = [{"id": 101, "status": "resolved"}, {"id": 103, "status": "new"}]
    mapping = {"101": "1", "103": "3"}
    destino = {"1": "closed", "3": "opened"}  # ya coincide con lo deseado

    result = plan_state_changes(origin, _STATUS_CFG, mapping, destino)
    assert result.changes == []
    assert result.already_ok == 2

    writer = _StateWriter()
    apply_state_changes(result, writer, mantis_project_id=_MANTIS_PROJECT_ID)

    assert writer.state_calls == []
    assert writer.comments == []
    assert result.applied == 0


# ── (c) simetría: reapertura ────────────────────────────────────────────────


def test_ticket_reabierto_en_mantis_reabre_el_issue_en_gitlab():
    origin = [{"id": 101, "status": "feedback"}]
    mapping = {"101": "1"}
    destino = {"1": "closed"}  # quedó cerrado de una corrida anterior

    result = plan_state_changes(origin, _STATUS_CFG, mapping, destino)
    assert len(result.changes) == 1
    assert result.changes[0].action == "reopen"
    assert result.to_reopen == 1

    writer = _StateWriter()
    apply_state_changes(result, writer, mantis_project_id=_MANTIS_PROJECT_ID)

    assert writer.state_calls == [("1", "opened")]
    # Reabrir NO deja nota de cierre.
    assert writer.comments == []


# ── (d) status sin mapeo => fallback DECLARADO ──────────────────────────────


def test_status_desconocido_cae_al_fallback_y_queda_declarado():
    origin = [{"id": 101, "status": "en_revision_interna"}]
    mapping = {"101": "1"}
    destino = {"1": "closed"}

    result = plan_state_changes(origin, _STATUS_CFG, mapping, destino)

    assert result.unmapped_status == ["101"]
    # El fallback es `opened`, y el destino está `closed`: se reabre.
    assert [c.desired_state for c in result.changes] == ["opened"]


# ── (e) ticket del origen todavía no migrado ────────────────────────────────


def test_ticket_no_migrado_se_reporta_y_no_se_toca():
    origin = [{"id": 101, "status": "resolved"}, {"id": 999, "status": "resolved"}]
    mapping = {"101": "1"}  # 999 no está migrado
    destino = {"1": "opened"}

    result = plan_state_changes(origin, _STATUS_CFG, mapping, destino)

    assert result.not_migrated == ["999"]
    assert [c.mantis_issue_id for c in result.changes] == ["101"]
    assert result.failed == []


# ── (f) un fallo no aborta la pasada ───────────────────────────────────────


def test_un_fallo_no_aborta_la_pasada():
    origin = [
        {"id": 101, "status": "resolved"},
        {"id": 102, "status": "resolved"},
        {"id": 103, "status": "resolved"},
    ]
    mapping = {"101": "1", "102": "2", "103": "3"}
    destino = {"1": "opened", "2": "opened", "3": "opened"}

    result = plan_state_changes(origin, _STATUS_CFG, mapping, destino)
    writer = _StateWriter(fail_iids={"2"})
    apply_state_changes(result, writer, mantis_project_id=_MANTIS_PROJECT_ID)

    assert result.applied == 2
    assert len(result.failed) == 1
    assert result.failed[0]["gitlab_iid"] == "2"
    assert result.failed[0]["op_kind"] == "apply_item_state"
    # Los otros dos SÍ se aplicaron pese al fallo del medio.
    assert sorted(iid for iid, _ in writer.state_calls) == ["1", "3"]


# ── (g) nota de trazabilidad de closed_at, una sola vez ────────────────────


def test_nota_de_cierre_se_agrega_una_sola_vez_y_declara_el_closed_at():
    origin = [{"id": 101, "status": "resolved"}]
    mapping = {"101": "1"}

    # 1ª corrida: destino abierto -> cierra y comenta.
    r1 = plan_state_changes(origin, _STATUS_CFG, mapping, {"1": "opened"})
    writer = _StateWriter()
    apply_state_changes(
        r1, writer, mantis_project_id=_MANTIS_PROJECT_ID,
        mantis_status_dates={"101": "2026-06-12"},
    )
    assert len(writer.comments) == 1
    cuerpo = writer.comments[0][1]
    assert "closed_at" in cuerpo
    assert "2026-06-12" in cuerpo
    assert f"stacky-migrated:mantis:{_MANTIS_PROJECT_ID}:101:state" in cuerpo

    # 2ª corrida sobre el MISMO writer, forzando otro cierre: el marcador ya
    # existe, así que no debe duplicar la nota.
    r2 = plan_state_changes(origin, _STATUS_CFG, mapping, {"1": "opened"})
    apply_state_changes(r2, writer, mantis_project_id=_MANTIS_PROJECT_ID)
    assert len(writer.comments) == 1


def test_closure_note_desactivada_no_comenta():
    origin = [{"id": 101, "status": "resolved"}]
    result = plan_state_changes(origin, _STATUS_CFG, {"101": "1"}, {"1": "opened"})
    writer = _StateWriter()
    apply_state_changes(
        result, writer, mantis_project_id=_MANTIS_PROJECT_ID, closure_note=False
    )
    assert writer.state_calls == [("1", "closed")]
    assert writer.comments == []


# ── (h) config inválida ────────────────────────────────────────────────────


def test_gitlab_state_invalido_en_config_se_declara_y_no_escribe():
    cfg = dict(_STATUS_CFG)
    cfg["resolved"] = {"gitlab_state": "cerrado", "label": "status::resolved"}
    origin = [{"id": 101, "status": "resolved"}]

    result = plan_state_changes(origin, cfg, {"101": "1"}, {"1": "opened"})

    assert result.changes == []
    assert len(result.failed) == 1
    assert "cerrado" in result.failed[0]["error"]


def test_estado_actual_ilegible_se_omite_por_seguridad():
    origin = [{"id": 101, "status": "resolved"}]
    # El destino no informó estado para el iid 1 (issue borrado a mano, p. ej.).
    result = plan_state_changes(origin, _STATUS_CFG, {"101": "1"}, {})

    assert result.changes == []
    assert len(result.failed) == 1
    assert "estado actual" in result.failed[0]["error"]


# ── (i) el barrido del destino incluye los CERRADOS ────────────────────────


def test_fetch_destination_states_incluye_los_cerrados():
    writer = _StateWriter(items=[
        {"iid": "1", "description": "x", "state": "closed"},
        {"iid": "2", "description": "y", "state": "opened"},
        {"iid": "", "description": "sin iid", "state": "opened"},
    ])

    states = fetch_destination_states(writer)

    assert states == {"1": "closed", "2": "opened"}


def test_apply_item_state_del_dryrun_writer_rechaza_estado_invalido():
    from tools.migrar_mantis_gitlab.destination_writer import DryRunGitLabWriter

    class _Cfg:
        base_url = "https://fake.local"
        project_path = "grupo/repo-demo"

    writer = DryRunGitLabWriter(_Cfg())
    with pytest.raises(ValueError):
        writer.apply_item_state("1", "cerrado")


def test_dryrun_writer_refleja_el_estado_simulado_en_fetch_open_items():
    from tools.migrar_mantis_gitlab.destination_writer import DryRunGitLabWriter

    class _Cfg:
        base_url = "https://fake.local"
        project_path = "grupo/repo-demo"

    writer = DryRunGitLabWriter(_Cfg())
    created = writer.create_item({"title": "t", "description": "d"})
    iid = created["iid"]

    assert fetch_destination_states(writer) == {iid: "opened"}

    writer.apply_item_state(iid, "closed")
    assert fetch_destination_states(writer) == {iid: "closed"}
