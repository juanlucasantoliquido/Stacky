"""
issue_provider.base — Contrato que cualquier backend de tickets debe cumplir.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from .types import CommentKind, Ticket, TicketDetail


class ProviderError(RuntimeError):
    """Error genérico del provider (auth, red, API, ...)."""


class TicketNotFound(ProviderError):
    """El ticket solicitado no existe o no es visible."""


class IssueProvider(ABC):
    """
    Contrato mínimo que debe implementar todo backend de tickets.

    Convenciones:
      - `id` es un string (aunque el backend use int lo castea).
      - `fetch_open_tickets` devuelve los tickets "accionables" para Stacky,
        el filtrado fino (por asignado, por área, etc.) vive dentro de cada
        implementación y se alimenta de `self._config`.
      - `add_comment(kind=CommentKind.XXX, ...)` publica una nota y, si el
        backend lo permite, puede disparar transiciones de estado asociadas
        (ej. ADO: `System.State` al agregar comentario QA_RESOLUTION).
      - `transition_state(...)` es opcional — si el backend no soporta la
        transición solicitada, devuelve `False` sin levantar excepción.
    """

    # Identificador corto del backend — "azure_devops" | ...
    name: str = ""

    def __init__(self, config: dict):
        self._config = config or {}

    # ── Discovery / sanity ───────────────────────────────────────────────

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """
        True, "" si el provider está configurado y accesible.
        False, "<motivo>" si falta credencial / endpoint / red.
        Se llama antes de arrancar ciclos — no debe costar más que un ping.
        """

    # ── Lectura ──────────────────────────────────────────────────────────

    @abstractmethod
    def fetch_open_tickets(self) -> list[Ticket]:
        """
        Lista de tickets abiertos/accionables para el usuario/proyecto actual.
        El orden se respeta aguas abajo (Stacky vuelve a priorizar por su cuenta).
        """

    @abstractmethod
    def fetch_ticket_detail(self, ticket_id: str) -> TicketDetail:
        """
        Descarga detalle completo de un ticket. Levanta TicketNotFound si no existe.
        """

    def fetch_ticket_ids_by_query(self, query: str) -> list[str]:
        """
        Ejecuta una query nativa del backend (WIQL en ADO, filtros nativos)
        y devuelve IDs. Implementación default vacía — los providers que lo
        soporten deben sobrescribir.
        """
        return []

    # ── Escritura ────────────────────────────────────────────────────────

    @abstractmethod
    def add_comment(
        self,
        ticket_id: str,
        body: str,
        kind: CommentKind = CommentKind.GENERIC,
        is_html: bool = False,
    ) -> bool:
        """Agrega una nota/comentario. True si se publicó."""

    def transition_state(self, ticket_id: str, target_state: str) -> bool:
        """
        Mueve el ticket a `target_state` usando el vocabulario nativo del backend
        (ej. "Resolved" en ADO, "resuelta").. El llamador es responsable
        de conocer los estados del backend — el provider NO normaliza de vuelta.
        Default: no-op (algunos backends no permiten transición por API).
        """
        return False

    def assign(self, ticket_id: str, user: str) -> bool:
        """Reasigna un ticket. Default: no-op."""
        return False

    def close(self, ticket_id: str, reason: str = "") -> bool:
        """Cierra un ticket. Default: intenta transicionar a estado 'Closed'."""
        return self.transition_state(ticket_id, "Closed")

    # ── Metadata ─────────────────────────────────────────────────────────

    def ticket_url(self, ticket_id: str) -> str:
        """URL canónica del ticket en el backend (para enlazar desde artefactos)."""
        return ""

    def state_mapping(self) -> dict[str, str]:
        """
        Mapeo estado_nativo → estado_normalizado Stacky
        ("asignada" | "aceptada" | "resuelta" | "completada" | "archivada").
        El provider puede leerlo de config para ser customizable.
        """
        return {}

    # ── Utilidades genéricas ─────────────────────────────────────────────

    @staticmethod
    def normalize_state(
        raw_state: str, mapping: dict[str, str], default: str = "asignada"
    ) -> str:
        """Aplica un mapping case-insensitive con fallback."""
        if not raw_state:
            return default
        low = raw_state.strip().lower()
        for k, v in mapping.items():
            if k.strip().lower() == low:
                return v
        return default
