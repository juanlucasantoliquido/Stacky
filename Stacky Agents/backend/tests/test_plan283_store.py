"""Plan 283 F2 - Las dos tablas del modulo de reuniones.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8). Sin
esto un pytest suelto escribe en la base VIVA del operador.
"""
from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _db():
    """La base en memoria VIVE todo el proceso: sin este vaciado, lo que crea un
    caso se filtra al siguiente y los conteos mienten (ya paso al escribirlo)."""
    import db

    db.init_db()
    with db.session_scope() as s:
        from services.meetings_store import Meeting, MeetingActionItem

        s.query(MeetingActionItem).delete(synchronize_session=False)
        s.query(Meeting).delete(synchronize_session=False)
    yield


def test_1_init_db_crea_las_dos_tablas():
    import db

    tablas = set(db.Base.metadata.tables)
    # Guard positivo: el metadata trae las tablas de siempre, o el assert
    # siguiente pasaria contra un metadata vacio.
    assert "tickets" in tablas and "agent_prompt_versions" in tablas
    assert "meetings" in tablas
    assert "meeting_action_items" in tablas


def test_2_la_terna_unica_rechaza_el_duplicado():
    from sqlalchemy.exc import IntegrityError

    from services import meetings_store as st

    st.create_meeting(project="P283", subject="Semanal", source="graph", external_id="ext-1")
    # Guard positivo: la MISMA terna con otro proyecto SI entra (o el rechazo de
    # abajo probaria que la tabla esta rota, no que la restriccion funciona).
    st.create_meeting(project="OTRO", subject="Semanal", source="graph", external_id="ext-1")

    with pytest.raises(IntegrityError):
        st.create_meeting(project="P283", subject="Semanal otra vez",
                          source="graph", external_id="ext-1")


def test_3_external_id_nulo_se_permite_varias_veces():
    """La fuente manual no tiene identificador externo: dos altas manuales del
    mismo proyecto no pueden chocar entre si."""
    from services import meetings_store as st

    a = st.create_meeting(project="P283", subject="Manual A")
    b = st.create_meeting(project="P283", subject="Manual B")
    assert a != b
    assert len(st.list_meetings("P283")) == 2


def test_4_to_dict_devuelve_exactamente_las_claves_del_contrato():
    from services.meetings_store import Meeting, MeetingActionItem

    reunion = Meeting(
        source="manual", external_id=None, stacky_project_name="P283",
        subject="Semanal", organizer="ana@x.com",
        started_at=datetime(2026, 8, 1, 14, 0, 0), ended_at=None, join_url=None,
        transcript_text="hola", transcript_format="txt",
        minutes_json="{}", minutes_state="done",
        created_at=datetime(2026, 8, 1, 13, 0, 0),
        updated_at=datetime(2026, 8, 1, 15, 0, 0),
    )
    assert set(reunion.to_dict()) == {
        "id", "source", "external_id", "stacky_project_name", "subject", "organizer",
        "started_at", "ended_at", "join_url", "transcript_format", "minutes_state",
        "created_at", "updated_at", "action_items_count",
    }
    # Los dos campos grandes NO viajan en el listado.
    assert "transcript_text" not in reunion.to_dict()
    assert "minutes_json" not in reunion.to_dict()
    # Fechas en ISO-8601 con Z.
    assert reunion.to_dict()["started_at"] == "2026-08-01T14:00:00Z"

    item = MeetingActionItem(
        meeting_id=1, titulo="Revisar informe", responsable="Ana",
        fecha_compromiso=datetime(2026, 8, 7), cita="lo reviso el viernes",
        atribucion="confirmada", estado="propuesto", tracker_type=None,
        external_id=None, created_at=datetime(2026, 8, 1),
    )
    assert set(item.to_dict()) == {
        "id", "meeting_id", "titulo", "responsable", "fecha_compromiso", "cita",
        "estado", "atribucion", "tracker_type", "external_id", "created_at",
    }
    assert item.to_dict()["fecha_compromiso"] == "2026-08-07T00:00:00Z"


def test_5_la_cita_es_obligatoria():
    from sqlalchemy.exc import IntegrityError

    import db
    from services.meetings_store import MeetingActionItem

    # Guard positivo: CON cita entra.
    with db.session_scope() as s:
        s.add(MeetingActionItem(meeting_id=1, titulo="ok", cita="dijo esto"))

    with pytest.raises(IntegrityError):
        with db.session_scope() as s:
            s.add(MeetingActionItem(meeting_id=1, titulo="sin respaldo", cita=None))


def test_6_borrar_la_reunion_borra_sus_pendientes_en_la_misma_sesion():
    """`meeting_id` NO declara ForeignKey y SQLite no aplica FK sin
    `PRAGMA foreign_keys=ON`, que este repo NO activa. Por lo tanto la cascada
    es RESPONSABILIDAD DEL CODIGO: `delete_meeting` borra los hijos PRIMERO y en
    la MISMA sesion que el padre. Este caso prueba esa disciplina, no una
    garantia del esquema — y lo dice con esas palabras a proposito.
    """
    import db
    from services import meetings_store as st
    from services.meetings_store import MeetingActionItem

    mid = st.create_meeting(project="P283", subject="Con pendientes")
    st.replace_action_items(mid, [
        {"titulo": "uno", "cita": "a", "atribucion": "sin_responsable"},
        {"titulo": "dos", "cita": "b", "atribucion": "sin_responsable"},
    ])
    otra = st.create_meeting(project="P283", subject="Vecina")
    st.replace_action_items(otra, [{"titulo": "tres", "cita": "c"}])

    with db.session_scope() as s:
        assert s.query(MeetingActionItem).filter_by(meeting_id=mid).count() == 2

    assert st.delete_meeting(mid) is True

    with db.session_scope() as s:
        assert s.query(MeetingActionItem).filter_by(meeting_id=mid).count() == 0
        # Y NO se lleva puestos los de la reunion vecina.
        assert s.query(MeetingActionItem).filter_by(meeting_id=otra).count() == 1


def test_7_minutes_state_nace_pending():
    from services import meetings_store as st

    mid = st.create_meeting(project="P283", subject="Recien creada")
    data = st.get_meeting_dict(mid, project="P283")
    assert data is not None
    assert data["minutes_state"] == "pending"
    assert data["action_items_count"] == 0
    # Y el proyecto equivocado no la ve.
    assert st.get_meeting_dict(mid, project="OTRO") is None
