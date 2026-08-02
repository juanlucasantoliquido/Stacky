"""Plan 283 F2 - Persistencia de reuniones, transcripciones, minutas y pendientes.

Dos tablas NUEVAS: `meetings` y `meeting_action_items`. Tablas nuevas =>
`Base.metadata.create_all` (db.py) las crea sin migracion destructiva. La UNICA
edicion en `db.py` es la linea de import dentro de `init_db()`: sin ella,
`create_all` no las ve.

TRAMPA VERIFICADA que este modulo evita a proposito: `db.py` tiene un
`_rebuild_tickets_table_if_needed(conn)` que reconstruye la tabla `tickets` con
una lista de columnas HARDCODEADA en dos lugares y hace `DROP TABLE tickets`.
Afecta UNICAMENTE a `tickets`. Por eso el vinculo con el tracker va al reves
(`MeetingActionItem.external_id`) y este plan NO agrega ninguna columna a
`tickets`: el rebuild la borraria en silencio junto con el dato del operador.

Toda escritura pasa por `run_with_retry` (db.py): en SQLite cualquier escritura
puede morir con `SQLITE_LOCKED`. Regla del docstring de `run_with_retry`: la
funcion que se le pasa DEBE abrir su propia sesion adentro; prohibido pasarle
una lambda con una `Session` ya abierta.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, run_with_retry, session_scope

# Estados de la minuta. `blocked` = el filtro de salida de datos no dejo mandar
# la transcripcion al modelo; NO es un error del modelo.
MINUTES_STATES = ("pending", "done", "failed", "blocked")
# Estados de un pendiente.
ITEM_STATES = ("propuesto", "publicado", "descartado")
# Resultado del cotejo del responsable contra los que hablaron (D9).
ATRIBUCIONES = ("confirmada", "sin_hablante", "sin_responsable")


def _iso(value: datetime | None) -> str | None:
    """ISO-8601 con `Z`. Los datetime se guardan naive UTC (convencion del repo)."""
    return value.isoformat() + "Z" if value else None


class Meeting(Base):
    """Una reunion, con su transcripcion cruda y su minuta destilada."""

    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)          # "manual" | "graph"
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stacky_project_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(400), nullable=False)
    organizer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # naive UTC
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    join_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_format: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "vtt"|"txt"
    minutes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    minutes_state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "stacky_project_name", "source", "external_id",
            name="uq_meetings_proyecto_fuente_externo",
        ),
        Index("ix_meetings_started_at", "started_at"),
    )

    def to_dict(self, action_items_count: int = 0) -> dict:
        """Contrato del LISTADO. `transcript_text` y `minutes_json` NO se
        serializan aca a proposito: son grandes y la minuta viaja por el detalle
        (`GET /meetings/<id>`). El conteo de pendientes lo aporta quien llama,
        que es el unico que tiene la sesion abierta."""
        return {
            "id": self.id,
            "source": self.source,
            "external_id": self.external_id,
            "stacky_project_name": self.stacky_project_name,
            "subject": self.subject,
            "organizer": self.organizer,
            "started_at": _iso(self.started_at),
            "ended_at": _iso(self.ended_at),
            "join_url": self.join_url,
            "transcript_format": self.transcript_format,
            "minutes_state": self.minutes_state,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "action_items_count": action_items_count,
        }


class MeetingActionItem(Base):
    """Un compromiso concreto que salio de una reunion.

    `meeting_id` NO declara `ForeignKey` — y aunque lo declarara, SQLite no
    aplica las FK sin `PRAGMA foreign_keys=ON`, que este repo no activa. El
    borrado en cascada es por lo tanto RESPONSABILIDAD DEL CODIGO
    (`delete_meeting`), no una garantia del esquema. Se dice asi de explicito
    para no declarar una garantia que la base no da.
    """

    __tablename__ = "meeting_action_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    titulo: Mapped[str] = mapped_column(String(400), nullable=False)
    responsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_compromiso: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cita: Mapped[str] = mapped_column(Text, nullable=False)   # D4: obligatoria, nunca vacia
    # D9 - resultado de cotejar `responsable` contra los que hablaron.
    atribucion: Mapped[str] = mapped_column(String(20), nullable=False, default="sin_responsable")
    estado: Mapped[str] = mapped_column(String(16), nullable=False, default="propuesto")
    tracker_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_action_items_meeting", "meeting_id"),)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "meeting_id": self.meeting_id,
            "titulo": self.titulo,
            "responsable": self.responsable,
            "fecha_compromiso": _iso(self.fecha_compromiso),
            "cita": self.cita,
            "estado": self.estado,
            "atribucion": self.atribucion,
            "tracker_type": self.tracker_type,
            "external_id": self.external_id,
            "created_at": _iso(self.created_at),
        }


# ── Operaciones (cada una abre su propia sesion: regla de run_with_retry) ─────

def create_meeting(
    *,
    project: str,
    subject: str,
    source: str = "manual",
    external_id: str | None = None,
    organizer: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    join_url: str | None = None,
) -> int:
    def _fn() -> int:
        with session_scope() as session:
            row = Meeting(
                source=source,
                external_id=external_id,
                stacky_project_name=project,
                subject=subject,
                organizer=organizer,
                started_at=started_at,
                ended_at=ended_at,
                join_url=join_url,
                minutes_state="pending",
            )
            session.add(row)
            session.flush()
            return int(row.id)

    return run_with_retry(_fn, label="meetings.create")


def get_meeting_dict(meeting_id: int, *, project: str | None = None) -> dict | None:
    """Detalle: reunion + minuta parseada + pendientes. `None` si no existe."""
    with session_scope() as session:
        row = session.get(Meeting, meeting_id)
        if row is None or (project and row.stacky_project_name != project):
            return None
        items = (
            session.query(MeetingActionItem)
            .filter(MeetingActionItem.meeting_id == meeting_id)
            .order_by(MeetingActionItem.id.asc())
            .all()
        )
        data = row.to_dict(action_items_count=len(items))
        minuta = None
        if row.minutes_json:
            try:
                minuta = json.loads(row.minutes_json)
            except Exception:  # noqa: BLE001 - una minuta corrupta no rompe la pantalla
                minuta = None
        data["minutes"] = minuta
        data["transcript_chars"] = len(row.transcript_text or "")
        data["action_items"] = [i.to_dict() for i in items]
        return data


def get_transcript(meeting_id: int) -> tuple[str, str] | None:
    """`(texto, formato)` de la transcripcion guardada, o `None` si no hay."""
    with session_scope() as session:
        row = session.get(Meeting, meeting_id)
        if row is None or not (row.transcript_text or "").strip():
            return None
        return row.transcript_text or "", row.transcript_format or "txt"


def list_meetings(project: str) -> list[dict]:
    """Reuniones del proyecto, `started_at` descendente (las sin fecha, al final)."""
    with session_scope() as session:
        rows = (
            session.query(Meeting)
            .filter(Meeting.stacky_project_name == project)
            .order_by(Meeting.started_at.desc().nullslast(), Meeting.id.desc())
            .all()
        )
        if not rows:
            return []
        conteos: dict[int, int] = {}
        for item in (
            session.query(MeetingActionItem)
            .filter(MeetingActionItem.meeting_id.in_([r.id for r in rows]))
            .all()
        ):
            conteos[item.meeting_id] = conteos.get(item.meeting_id, 0) + 1
        return [r.to_dict(action_items_count=conteos.get(r.id, 0)) for r in rows]


def save_transcript(meeting_id: int, *, content: str, fmt: str) -> bool:
    def _fn() -> bool:
        with session_scope() as session:
            row = session.get(Meeting, meeting_id)
            if row is None:
                return False
            row.transcript_text = content
            row.transcript_format = fmt
            row.updated_at = datetime.utcnow()
            return True

    return run_with_retry(_fn, label="meetings.save_transcript")


def set_minutes(meeting_id: int, *, minutes: dict | None, state: str) -> bool:
    """Guarda la minuta y su estado. `minutes=None` deja lo guardado intacto: la
    transcripcion NUNCA se pierde por un fallo del modelo (D8)."""
    def _fn() -> bool:
        with session_scope() as session:
            row = session.get(Meeting, meeting_id)
            if row is None:
                return False
            if minutes is not None:
                row.minutes_json = json.dumps(minutes, ensure_ascii=False)
            row.minutes_state = state
            row.updated_at = datetime.utcnow()
            return True

    return run_with_retry(_fn, label="meetings.set_minutes")


def replace_action_items(meeting_id: int, pendientes: list[dict]) -> int:
    """Reemplaza los pendientes de una reunion (re-destilar es idempotente).

    Los ya publicados se CONSERVAN: borrarlos dejaria huerfano un work item que
    ya existe en el sistema del operador.
    """
    def _fn() -> int:
        with session_scope() as session:
            (
                session.query(MeetingActionItem)
                .filter(
                    MeetingActionItem.meeting_id == meeting_id,
                    MeetingActionItem.estado != "publicado",
                )
                .delete(synchronize_session=False)
            )
            creados = 0
            for p in pendientes:
                session.add(MeetingActionItem(
                    meeting_id=meeting_id,
                    titulo=str(p.get("titulo") or "")[:400],
                    responsable=p.get("responsable"),
                    fecha_compromiso=p.get("fecha_compromiso"),
                    cita=str(p.get("cita") or ""),
                    atribucion=str(p.get("atribucion") or "sin_responsable"),
                    estado="propuesto",
                ))
                creados += 1
            return creados

    return run_with_retry(_fn, label="meetings.replace_items")


def get_action_item_dict(item_id: int) -> dict | None:
    with session_scope() as session:
        row = session.get(MeetingActionItem, item_id)
        return row.to_dict() if row else None


def mark_item_published(item_id: int, *, tracker_type: str, external_id: str) -> bool:
    def _fn() -> bool:
        with session_scope() as session:
            row = session.get(MeetingActionItem, item_id)
            if row is None:
                return False
            row.estado = "publicado"
            row.tracker_type = tracker_type
            row.external_id = str(external_id)
            return True

    return run_with_retry(_fn, label="meetings.mark_published")


def delete_meeting(meeting_id: int) -> bool:
    """Borra la reunion Y sus pendientes, EN LA MISMA SESION y los hijos PRIMERO.

    No hay `ForeignKey` ni `ON DELETE CASCADE`: SQLite no aplica las FK sin
    `PRAGMA foreign_keys=ON` y este repo no lo activa. La cascada es disciplina
    de codigo, y este es el unico lugar que la implementa.
    """
    def _fn() -> bool:
        with session_scope() as session:
            row = session.get(Meeting, meeting_id)
            if row is None:
                return False
            (
                session.query(MeetingActionItem)
                .filter(MeetingActionItem.meeting_id == meeting_id)
                .delete(synchronize_session=False)
            )
            session.delete(row)
            return True

    return run_with_retry(_fn, label="meetings.delete")
