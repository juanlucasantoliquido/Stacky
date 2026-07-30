"""tests/test_mg_reanudacion.py — reanudar una corrida cortada sin duplicar ni
dejar huecos.

## Por qué importa ahora

La migración pasa de 52 a **1008 issues** (más ~2.600 notas, adjuntos,
relaciones y 956 cierres). Una corrida así se corta: por un 429, por la sesión de
Mantis, por la red. La pregunta que hay que poder responder es *"¿reanudar es
seguro?"*, y antes de estos cambios la respuesta era **no**, de dos formas
distintas y ambas silenciosas:

**Modo de falla A — DUPLICADO.** La corrida 1 crea el issue (mapeo `done`) y
después una de sus notas falla: el `except` de `execute_migration` marca el
TICKET como `partial`. Al reanudar, `plan_migration` no saltea los `partial`
(solo los `done`), así que vuelve a emitir el `create_item`; con `live_map` como
única barrera (`partial` != `done`) se creaba un SEGUNDO issue para el mismo
ticket de Mantis.

**Modo de falla B — HUECO.** Si en cambio la rehidratación corre primero (que es
lo que hace `cmd_execute`), encuentra el marcador en GitLab y subía el ticket de
`partial` a `done`. Entonces `plan_migration` saltea el ticket COMPLETO y las
notas que faltaban **no se re-planifican nunca**. Nada avisa.

Los dos se arreglan con dos reglas:
1. `_apply_create_item` decide "ya existe" por el **`gitlab_iid` mapeado**, no por
   el `status` (que refleja si faltan ops).
2. `hydrate_map_from_destination_mg` **no degrada** `partial`/`failed`/`pending` a
   `done`.
"""
from __future__ import annotations

import pytest

from tools.migrar_mantis_gitlab import migrator_mg_map as mg_map
from tools.migrar_mantis_gitlab.migrator_mg_core import MgMigrationOp, MgMigrationPlan
from tools.migrar_mantis_gitlab.migrator_mg_executor import (
    execute_migration,
    hydrate_map_from_destination_mg,
)
from tests.test_mg_executor import _FakeWriter, _marker

_PROJECT_PATH = "grupo/repo-demo"
_MANTIS_PROJECT_ID = "310"


@pytest.fixture
def conn(tmp_path):
    c = mg_map.open_map_db(str(tmp_path / "map.sqlite3"))
    yield c
    c.close()


def _op_create(issue_id: str) -> MgMigrationOp:
    return MgMigrationOp(
        op_kind="create_item", mantis_issue_id=issue_id, dest_parent_mantis_id=None,
        payload={"title": f"t-{issue_id}", "description": ""}, marker=_marker(issue_id),
    )


def _op_nota(issue_id: str, n: int) -> MgMigrationOp:
    return MgMigrationOp(
        op_kind="post_comment", mantis_issue_id=issue_id, dest_parent_mantis_id=None,
        payload={"body": f"nota {n} de {issue_id}"},
        marker=f"<!-- stacky-migrated:mantis:{_MANTIS_PROJECT_ID}:{issue_id}:note:{n} -->",
    )


def _plan(*ops) -> MgMigrationPlan:
    return MgMigrationPlan(ops=list(ops), counts_by_type={}, warnings=[], skipped_at_plan=0)


def _ejecutar(plan, writer, conn):
    return execute_migration(
        plan, writer, conn,
        project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
        checkpoint_path="", checkpoint_every=10,
    )


# ── Modo de falla A: DUPLICADO ─────────────────────────────────────────────


def test_reanudar_tras_nota_fallida_NO_duplica_el_issue(conn):
    """Corrida 1: issue creado + nota que falla -> ticket queda `partial`.
    Corrida 2: el issue NO debe crearse de nuevo."""

    class WriterNotaRota(_FakeWriter):
        def __init__(self):
            super().__init__()
            self.fallar_notas = True

        def post_comment(self, item_iid, body, created_at=None):
            if self.fallar_notas:
                raise RuntimeError("fallo simulado en la nota")
            return super().post_comment(item_iid, body, created_at)

    w = WriterNotaRota()
    plan = _plan(_op_create("101"), _op_nota("101", 1))

    r1 = _ejecutar(plan, w, conn)
    assert len(w.created) == 1
    assert len(r1.failed) == 1
    fila = mg_map.get_full_mapping(conn, _PROJECT_PATH)[0]
    assert fila["status"] == "partial", "una nota fallida debe dejar el ticket pendiente"
    assert fila["gitlab_iid"], "el gitlab_iid debe quedar registrado igual"

    # Corrida 2: el plan vuelve a incluir el create (no es `done`).
    w.fallar_notas = False
    r2 = _ejecutar(plan, w, conn)

    assert len(w.created) == 1, "NO debe crear un segundo issue para el mismo ticket"
    assert r2.skipped >= 1
    # Y la nota que faltaba SÍ se aplicó: eso es no dejar hueco.
    assert len(w.comments) == 1


def test_dos_corridas_seguidas_sin_fallos_no_duplican(conn):
    w = _FakeWriter()
    plan = _plan(_op_create("101"), _op_create("102"))
    _ejecutar(plan, w, conn)
    _ejecutar(plan, w, conn)
    assert len(w.created) == 2


# ── Modo de falla B: HUECO ─────────────────────────────────────────────────


def test_la_rehidratacion_NO_degrada_partial_a_done(conn):
    """Encontrar el issue en GitLab prueba que el ISSUE existe, no que sus notas
    se migraron. Si la rehidratación lo sube a `done`, `plan_migration` saltea el
    ticket completo y las notas faltantes se pierden en silencio."""
    mg_map.upsert_mapping(
        conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
        mantis_issue_id="101", gitlab_iid="501", status="partial",
    )

    class Stub(_FakeWriter):
        def fetch_open_items(self):
            return [{"iid": "501", "description": f"x\n\n{_marker('101')}", "state": "opened"}]

    mapping = hydrate_map_from_destination_mg(
        Stub(), conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
    )
    assert mapping["101"] == "partial", "el estado pendiente TIENE que sobrevivir"


def test_la_rehidratacion_si_marca_done_lo_que_no_tenia_estado(conn):
    """El caso normal: el SQLite se perdió y GitLab es la fuente de verdad."""

    class Stub(_FakeWriter):
        def fetch_open_items(self):
            return [
                {"iid": "501", "description": f"a\n\n{_marker('101')}", "state": "opened"},
                {"iid": "502", "description": f"b\n\n{_marker('102')}", "state": "closed"},
            ]

    mapping = hydrate_map_from_destination_mg(
        Stub(), conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
    )
    assert mapping == {"101": "done", "102": "done"}


def test_la_rehidratacion_registra_el_iid_aunque_conserve_el_estado(conn):
    """El `gitlab_iid` es lo que evita el duplicado, así que debe actualizarse
    incluso cuando el `status` se conserva como pendiente."""
    mg_map.upsert_mapping(
        conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
        mantis_issue_id="101", gitlab_iid=None, status="failed",
    )

    class Stub(_FakeWriter):
        def fetch_open_items(self):
            return [{"iid": "777", "description": f"x\n\n{_marker('101')}", "state": "opened"}]

    hydrate_map_from_destination_mg(
        Stub(), conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
    )
    fila = mg_map.get_full_mapping(conn, _PROJECT_PATH)[0]
    assert fila["gitlab_iid"] == "777"
    assert fila["status"] == "failed"


def test_ciclo_completo_rehidratar_y_reanudar_sin_duplicar_ni_dejar_hueco(conn):
    """El escenario end-to-end que va a ocurrir en la corrida de 1008:
    cae a mitad, se rehidrata desde GitLab, se reanuda."""

    class WriterNotaRota(_FakeWriter):
        def __init__(self):
            super().__init__()
            self.fallar_notas = True

        def post_comment(self, item_iid, body, created_at=None):
            if self.fallar_notas:
                raise RuntimeError("corte simulado")
            return super().post_comment(item_iid, body, created_at)

    w = WriterNotaRota()
    plan = _plan(_op_create("101"), _op_nota("101", 1), _op_nota("101", 2))

    _ejecutar(plan, w, conn)
    assert len(w.created) == 1 and len(w.comments) == 0

    # Se "pierde" el SQLite y se reconstruye desde el destino.
    hydrate_map_from_destination_mg(
        w, conn, project_path=_PROJECT_PATH, mantis_project_id=_MANTIS_PROJECT_ID,
    )

    w.fallar_notas = False
    r = _ejecutar(plan, w, conn)

    assert len(w.created) == 1, "sin duplicado"
    assert len(w.comments) == 2, "sin hueco: las 2 notas terminaron migradas"
    assert r.applied == 2
