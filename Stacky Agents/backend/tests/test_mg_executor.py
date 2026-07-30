"""tests/test_mg_executor.py — Plan 217 Batch 4, F5b.

Valida `tools/migrar_mantis_gitlab/migrator_mg_executor.py`:
  (a) idempotencia — re-ejecutar el mismo plan no duplica nada.
  (b) corte simulado — ejecutar la mitad, "perder" el SQLite local, y
      verificar que `hydrate_map_from_destination_mg` (leyendo el destino,
      NO el checkpoint) permite completar el resto sin duplicar.
  (c) un error en 1 op no aborta la corrida — el resto se aplica igual.
  (d) `hydrate_map_from_destination_mg` reconstruye el mapeo parseando
      markers de una lista de items fake.
  (e) `resume_migration` delega en `execute_migration` (checkpoint es solo
      informativo).

Escribe el SQLite en `tmp_path` (pytest), nunca en disco compartido.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab import migrator_mg_map as mg_map
from tools.migrar_mantis_gitlab import run_state
from tools.migrar_mantis_gitlab.destination_writer import DestinationWriter
from tools.migrar_mantis_gitlab.migrator_mg_core import MgMigrationOp, MgMigrationPlan
from tools.migrar_mantis_gitlab.migrator_mg_executor import (
    execute_migration,
    hydrate_map_from_destination_mg,
    resume_migration,
)

_PROJECT_PATH = "grupo/repo-demo"
_MANTIS_PROJECT_ID = "310"


def _marker(issue_id: str, *, project_id: str = _MANTIS_PROJECT_ID) -> str:
    return f"<!-- stacky-migrated:mantis:{project_id}:{issue_id} -->"


class _FakeWriter(DestinationWriter):
    """Fake completo de `DestinationWriter` (no `DryRunGitLabWriter`, para
    poder inyectar fallos controlados en `create_item` — test (c))."""

    def __init__(self, *, fail_titles: "set[str] | None" = None) -> None:
        self.created: list[dict] = []
        self.comments: list[tuple[str, str]] = []
        self.comment_dates: list = []
        self.milestones: list = []
        self.updated_at_calls: list = []
        self.states: dict[str, str] = {}
        self._counter = 0
        self._fail_titles = fail_titles or set()

    def create_item(self, payload: dict) -> dict:
        title = payload.get("title")
        if title in self._fail_titles:
            raise RuntimeError(f"fallo simulado creando {title!r}")
        self._counter += 1
        iid = f"iid-{self._counter}"
        self.created.append({**payload, "iid": iid})
        return {"iid": iid}

    def post_comment(self, item_iid: str, body: str, created_at: "str | None" = None) -> dict:
        # `created_at` es parte del contrato desde que el executor backdatea las
        # notas. Sin este parámetro el fake lanzaba TypeError, que el `except` de
        # `execute_migration` capturaba como un `failed` cualquiera: el test
        # seguía verde mientras NINGUNA nota se aplicaba. Falso verde clásico.
        self.comments.append((item_iid, body))
        self.comment_dates.append(created_at)
        return {"id": f"comment-{len(self.comments)}"}

    def upload_attachment(self, file_path: str, filename: str) -> dict:
        return {"url": f"/uploads/{filename}"}

    def link_attachment(self, item_iid: str, attachment_meta: dict) -> dict:
        return {"iid": item_iid}

    def create_issue_link(self, source_iid: str, target_iid: str, link_type: str) -> dict:
        return {"id": "link-1"}

    def ensure_milestone(self, title):
        self.milestones.append(title)
        return 9001

    def apply_item_state(
        self, item_iid: str, desired_state: str, updated_at: "str | None" = None
    ) -> dict:
        self.updated_at_calls.append(updated_at)
        self.states[str(item_iid)] = desired_state
        return {"iid": str(item_iid), "state": desired_state}

    def fetch_states(self) -> list[str]:
        return []

    def fetch_open_items(self) -> list[dict]:
        return [
            {
                "iid": c["iid"],
                "description": c.get("description", ""),
                "state": self.states.get(str(c["iid"]), "opened"),
            }
            for c in self.created
        ]

    def comment_exists(self, item_iid: str, marker: str) -> bool:
        return any(iid == item_iid and marker in body for iid, body in self.comments)

    def effective_target(self) -> tuple[str, str]:
        return ("https://fake.local", _PROJECT_PATH)


def _make_op(issue_id: str, *, parent: "str | None" = None) -> MgMigrationOp:
    return MgMigrationOp(
        op_kind="create_item",
        mantis_issue_id=issue_id,
        dest_parent_mantis_id=parent,
        payload={"title": f"title-{issue_id}", "description": ""},
        marker=_marker(issue_id),
    )


def _make_plan(issue_ids: list[str]) -> MgMigrationPlan:
    ops = [_make_op(i) for i in issue_ids]
    return MgMigrationPlan(
        ops=ops,
        counts_by_type={"create_item": len(ops)},
        warnings=[],
        skipped_at_plan=0,
    )


@pytest.fixture
def conn(tmp_path):
    connection = mg_map.open_map_db(str(tmp_path / "map.sqlite3"))
    yield connection
    connection.close()


# ── (a) idempotencia: re-ejecutar no duplica ────────────────────────────


def test_execute_migration_idempotente_re_ejecutar_no_duplica(conn, tmp_path):
    plan = _make_plan(["1", "2", "3"])
    writer = _FakeWriter()
    checkpoint_path = str(tmp_path / "checkpoint.json")

    result1 = execute_migration(
        plan, writer, conn,
        project_path=_PROJECT_PATH,
        mantis_project_id=_MANTIS_PROJECT_ID,
        checkpoint_path=checkpoint_path,
    )
    assert result1.applied == 3
    assert result1.skipped == 0
    assert len(writer.created) == 3

    result2 = execute_migration(
        plan, writer, conn,
        project_path=_PROJECT_PATH,
        mantis_project_id=_MANTIS_PROJECT_ID,
        checkpoint_path=checkpoint_path,
    )
    assert result2.applied == 0
    assert result2.skipped == 3
    # El writer NO recibió nuevas llamadas a create_item.
    assert len(writer.created) == 3


# ── (b) corte simulado + rehidratación desde el destino ─────────────────


def test_resume_tras_corte_rehidrata_desde_destino_no_desde_checkpoint(tmp_path):
    plan_first_half = _make_plan(["1", "2"])
    plan_full = _make_plan(["1", "2", "3", "4"])
    writer = _FakeWriter()
    checkpoint_path = str(tmp_path / "checkpoint.json")

    conn1 = mg_map.open_map_db(str(tmp_path / "map1.sqlite3"))
    try:
        result_partial = execute_migration(
            plan_first_half, writer, conn1,
            project_path=_PROJECT_PATH,
            mantis_project_id=_MANTIS_PROJECT_ID,
            checkpoint_path=checkpoint_path,
            checkpoint_every=1,
        )
        assert result_partial.applied == 2
    finally:
        conn1.close()

    # Checkpoint quedó guardado (informativo) tras la corrida parcial.
    checkpoint = run_state.load_checkpoint(checkpoint_path)
    assert checkpoint is not None
    assert checkpoint["last_mantis_issue_id"] == "2"

    # "Se pierde" el SQLite local: conn2 es una base NUEVA y vacía. La
    # única fuente de verdad que sobrevive es lo que el writer (destino)
    # ya tiene creado (writer.created, con el marker en la descripción).
    conn2 = mg_map.open_map_db(str(tmp_path / "map2.sqlite3"))
    try:
        rehydrated = hydrate_map_from_destination_mg(
            writer, conn2,
            project_path=_PROJECT_PATH,
            mantis_project_id=_MANTIS_PROJECT_ID,
        )
        assert rehydrated.get("1") == "done"
        assert rehydrated.get("2") == "done"
        assert "3" not in rehydrated
        assert "4" not in rehydrated

        result_rest = execute_migration(
            plan_full, writer, conn2,
            project_path=_PROJECT_PATH,
            mantis_project_id=_MANTIS_PROJECT_ID,
            checkpoint_path=str(tmp_path / "checkpoint2.json"),
        )
        assert result_rest.applied == 2  # solo 3 y 4
        assert result_rest.skipped == 2  # 1 y 2 ya estaban done
        assert len(writer.created) == 4  # nunca se duplicaron 1/2
        created_ids = sorted(c["title"] for c in writer.created)
        assert created_ids == ["title-1", "title-2", "title-3", "title-4"]
    finally:
        conn2.close()


def test_resume_migration_delega_en_execute_migration_y_loguea_checkpoint(tmp_path):
    plan = _make_plan(["1", "2"])
    writer = _FakeWriter()
    checkpoint_path = str(tmp_path / "checkpoint.json")
    conn = mg_map.open_map_db(str(tmp_path / "map.sqlite3"))
    try:
        run_state.save_checkpoint(checkpoint_path, last_mantis_issue_id="0", run_id="run-x")

        result = resume_migration(
            plan, writer, conn,
            project_path=_PROJECT_PATH,
            mantis_project_id=_MANTIS_PROJECT_ID,
            checkpoint_path=checkpoint_path,
        )
        assert result.applied == 2
        assert len(writer.created) == 2

        # Re-correr resume_migration sobre el mismo plan/conn no duplica
        # (delega en la misma idempotencia de execute_migration).
        result2 = resume_migration(
            plan, writer, conn,
            project_path=_PROJECT_PATH,
            mantis_project_id=_MANTIS_PROJECT_ID,
            checkpoint_path=checkpoint_path,
        )
        assert result2.applied == 0
        assert result2.skipped == 2
    finally:
        conn.close()


# ── (c) un error por-op no aborta el resto ───────────────────────────────


def test_error_en_una_op_no_aborta_el_resto(conn, tmp_path):
    plan = _make_plan(["1", "2", "3"])
    writer = _FakeWriter(fail_titles={"title-2"})
    checkpoint_path = str(tmp_path / "checkpoint.json")

    result = execute_migration(
        plan, writer, conn,
        project_path=_PROJECT_PATH,
        mantis_project_id=_MANTIS_PROJECT_ID,
        checkpoint_path=checkpoint_path,
    )

    assert result.applied == 2
    assert len(result.failed) == 1
    assert result.failed[0]["mantis_issue_id"] == "2"
    assert result.failed[0]["op_kind"] == "create_item"

    # 1 y 3 SÍ se crearon (el resto de la corrida continuó).
    created_titles = sorted(c["title"] for c in writer.created)
    assert created_titles == ["title-1", "title-3"]

    # El ticket 2 queda "partial" en el mapeo, NO "done" — reintentable.
    mapping_rows = {
        row["mantis_issue_id"]: row["status"] for row in mg_map.get_full_mapping(conn, _PROJECT_PATH)
    }
    assert mapping_rows["1"] == "done"
    assert mapping_rows["2"] == "partial"
    assert mapping_rows["3"] == "done"


# ── (d) hydrate_map_from_destination_mg reconstruye desde markers ───────


class _StubFetchOnlyWriter(DestinationWriter):
    """Stub mínimo para probar `hydrate_map_from_destination_mg` de forma
    aislada, sin pasar por `execute_migration`."""

    def __init__(self, items: list[dict]) -> None:
        self._items = items

    def create_item(self, payload):
        raise AssertionError("hydrate no debe escribir nada")

    def post_comment(self, item_iid, body, created_at=None):
        raise AssertionError("hydrate no debe escribir nada")

    def upload_attachment(self, file_path, filename):
        raise AssertionError("hydrate no debe escribir nada")

    def link_attachment(self, item_iid, attachment_meta):
        raise AssertionError("hydrate no debe escribir nada")

    def create_issue_link(self, source_iid, target_iid, link_type):
        raise AssertionError("hydrate no debe escribir nada")

    def ensure_milestone(self, title):
        raise AssertionError("hydrate no debe escribir nada")

    def apply_item_state(self, item_iid, desired_state, updated_at=None):
        raise AssertionError("hydrate no debe escribir nada")

    def fetch_states(self):
        return []

    def fetch_open_items(self):
        return self._items

    def comment_exists(self, item_iid, marker):
        return False

    def effective_target(self):
        return ("https://fake.local", _PROJECT_PATH)


def test_hydrate_map_from_destination_mg_reconstruye_por_marker(conn):
    writer = _StubFetchOnlyWriter([
        {"iid": "501", "description": f"desc issue 42\n\n{_marker('42')}"},
        {"iid": "502", "description": f"desc issue 43\n\n{_marker('43')}"},
        # Item de OTRO proyecto Mantis (project_id distinto) — no debe
        # matchear el regex acotado a _MANTIS_PROJECT_ID.
        {"iid": "503", "description": f"desc otro proyecto\n\n{_marker('99', project_id='311')}"},
        # Item sin marker (issue creado a mano en GitLab, no por esta
        # herramienta) — se ignora, no rompe nada.
        {"iid": "504", "description": "issue manual sin relación con Mantis"},
    ])

    mapping = hydrate_map_from_destination_mg(
        writer, conn,
        project_path=_PROJECT_PATH,
        mantis_project_id=_MANTIS_PROJECT_ID,
    )

    assert mapping == {"42": "done", "43": "done"}
    assert mg_map.get_gitlab_iid(
        conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID, mantis_issue_id="42"
    ) == "501"
    assert mg_map.get_gitlab_iid(
        conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID, mantis_issue_id="43"
    ) == "502"


# ── (f) un adjunto que FALLA no puede contarse como aplicado ────────────
#
# Regresión de la migración de Ripley del 2026-07-29: `migrate_attachment_mg`
# NUNCA propaga una excepción — atrapa todo y devuelve
# `{"skipped": False, "verified": False, "error": ...}`. El executor sólo
# miraba `skipped`, así que un adjunto que NO se subió sumaba a `applied`.
# Resultado real: el TLS contra Mantis estaba roto, fallaron los 1419
# adjuntos del proyecto, y el reporte los declaró aplicados. Cero adjuntos
# migrados, reporte en verde.


class _WriterAdjuntoRoto(_FakeWriter):
    def upload_attachment(self, file_path: str, filename: str) -> dict:
        raise RuntimeError("SSLError simulado bajando/subiendo el adjunto")


def _plan_con_adjunto() -> MgMigrationPlan:
    create = _make_op("42")
    attach = MgMigrationOp(
        op_kind="upload_attachment",
        mantis_issue_id="42",
        dest_parent_mantis_id=None,
        payload={"attachment_meta": {"id": "777", "name": "captura.png", "size": 10}},
        marker="<!-- stacky-migrated:mantis-file:310:42:777 -->",
    )
    return MgMigrationPlan(
        ops=[create, attach],
        counts_by_type={"create_item": 1, "upload_attachment": 1},
        warnings=[],
        skipped_at_plan=0,
    )


class _AdapterFake:
    def download_attachment_binary(self, file_id):
        return b"bytes"


def test_adjunto_fallido_cuenta_como_failed_no_como_applied(conn, tmp_path):
    writer = _WriterAdjuntoRoto()
    result = execute_migration(
        _plan_con_adjunto(), writer, conn,
        project_path=_PROJECT_PATH,
        mantis_project_id=_MANTIS_PROJECT_ID,
        checkpoint_path=str(tmp_path / "cp.json"),
        origin_adapter=_AdapterFake(),
        attachment_options={"max_size_mb": 50, "skip_if_over_limit": True},
    )

    # Se creó el issue (1 applied) pero el adjunto NO: no puede haber 2.
    assert result.applied == 1, (
        f"el adjunto falló y se contó como aplicado (applied={result.applied})"
    )
    assert len(result.failed) == 1
    assert result.failed[0]["op_kind"] == "upload_attachment"
    assert "captura.png" in result.failed[0]["error"]
    # El ticket queda 'partial' para que la corrida siguiente lo reintente.
    assert mg_map.get_full_mapping(conn, _PROJECT_PATH)[0]["status"] == "partial"


def test_adjunto_ya_presente_se_saltea_y_no_se_vuelve_a_subir(conn, tmp_path):
    """Idempotencia: si `attachment_exists` dice que ya está, no se re-sube
    (antes no había chequeo alguno y la descripción acumulaba duplicados)."""
    subidas: list = []

    class _WriterConAdjuntoYaPresente(_FakeWriter):
        def attachment_exists(self, item_iid, marker, filename=""):
            return True

        def upload_attachment(self, file_path: str, filename: str) -> dict:
            subidas.append(filename)
            return {"url": f"/uploads/{filename}"}

    writer = _WriterConAdjuntoYaPresente()
    result = execute_migration(
        _plan_con_adjunto(), writer, conn,
        project_path=_PROJECT_PATH,
        mantis_project_id=_MANTIS_PROJECT_ID,
        checkpoint_path=str(tmp_path / "cp.json"),
        origin_adapter=_AdapterFake(),
        attachment_options={"max_size_mb": 50, "skip_if_over_limit": True},
    )

    assert subidas == [], "no debe re-subirse un adjunto que ya está en el destino"
    assert result.skipped == 1
    assert result.failed == []
