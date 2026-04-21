"""
issue_provider.types — Dataclasses neutrales al backend.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CommentKind(str, Enum):
    """Tipos semánticos de nota/comentario que Stacky publica contra el tracker."""
    PM_CONFIRM = "pm_confirm"           # Post-PM: análisis completo
    QA_RESOLUTION = "qa_resolution"     # Post-QA: veredicto final
    GENERIC = "generic"                 # Nota libre


@dataclass
class TicketComment:
    """Una nota/comentario de un ticket."""
    id: str = ""
    author: str = ""
    created_at: str = ""       # ISO 8601
    body: str = ""             # texto plano o HTML (depende del tracker)
    is_html: bool = False


@dataclass
class TicketAttachment:
    """Un adjunto asociado al ticket."""
    id: str = ""
    filename: str = ""
    size_bytes: int = 0
    url: str = ""              # URL de descarga (requiere auth)
    content_type: str = ""


@dataclass
class Ticket:
    """
    Resumen ligero de un ticket — el tipo que devuelve listar/buscar.
    El "estado_normalizado" es el bucket semántico que usa Stacky para ruteo
    de carpetas: asignada | aceptada | resuelta | completada | archivada.
    """
    id: str
    title: str = ""
    state_raw: str = ""              # estado tal cual lo devuelve el tracker
    state_normalized: str = ""       # mapeado al vocabulario de Stacky
    severity: str = ""
    priority: int | None = None      # 1 = máxima, 5 = mínima
    category: str = ""
    assignee: str = ""
    last_modified: str = ""          # ISO 8601
    url: str = ""                    # enlace directo al ticket en el tracker
    raw: dict[str, Any] = field(default_factory=dict)  # payload crudo del backend


@dataclass
class TicketDetail:
    """Detalle completo — lo que se serializa al INC-{id}.md."""
    ticket: Ticket
    description: str = ""            # puede ser HTML (ADO) o texto plano
    description_is_html: bool = False
    reproduction_steps: str = ""
    additional_info: str = ""
    comments: list[TicketComment] = field(default_factory=list)
    attachments: list[TicketAttachment] = field(default_factory=list)
    # Campos extra del backend (acceptance_criteria, tags, area_path, iteration_path, ...)
    extra: dict[str, Any] = field(default_factory=dict)
