"""tools/migrar_mantis_gitlab/adapters/base.py — Plan 217 F0.

Interfaz abstracta `MantisReadAdapter`: contrato mínimo que deben implementar
los adaptadores de lectura de origen (F2b scraping, F2a API), para que el
núcleo de migración (`migrator_mg_*.py`, fases posteriores) sea agnóstico de
cómo se extraen los datos de Mantis.

Este archivo es SOLO el contrato (firmas + NotImplementedError). Ninguna
implementación concreta vive acá — eso es de F2a/F2b, fuera de este batch.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MantisReadAdapter(ABC):
    """Contrato de lectura de origen (Mantis), independiente del mecanismo
    de extracción (API REST/SOAP o web-scraping)."""

    @abstractmethod
    def fetch_all_issues(self) -> list[dict[str, Any]]:
        """Devuelve todos los issues del/de los proyecto(s) configurados."""
        raise NotImplementedError

    @abstractmethod
    def fetch_comments(self, issue_id: int) -> list[dict[str, Any]]:
        """Devuelve los comentarios/bugnotes de un issue puntual."""
        raise NotImplementedError

    @abstractmethod
    def fetch_attachments(self, issue_id: int) -> list[dict[str, Any]]:
        """Devuelve los metadatos de adjuntos de un issue puntual."""
        raise NotImplementedError

    @abstractmethod
    def fetch_relationships(self, issue_id: int) -> list[dict[str, Any]]:
        """Devuelve las relaciones (parent/child/related/duplicate/depends)
        de un issue puntual."""
        raise NotImplementedError

    @abstractmethod
    def download_attachment_binary(self, file_id: "str | int") -> bytes:
        """Descarga el binario crudo de un adjunto Mantis (Plan 217 Batch 4,
        F6a). Firma alineada a la que YA existía como extensión no-abstracta
        en `MantisApiReadAdapter` (`download_attachment_binary(file_id)`,
        delegando a `MantisClient.download_attachment_binary`, con test
        propio `test_mg_adapters_api.py` ya en verde antes de este batch) —
        se promueve a abstracta acá (polimorfismo en vez de `isinstance` en
        `migrator_mg_attachments.py`) y se implementa también en
        `MantisWebScrapingReadAdapter` (vía la sesión/cookie autenticada de
        `get_session()`, C7 del plan: "requieren cookie de sesión, no hay
        endpoint anónimo"). Recibe `file_id`, NO el dict completo del
        adjunto — el caller (`migrator_mg_attachments.
        download_mg_attachment_to_temp`) extrae `attachment_meta["id"]`
        antes de llamar, para no romper la firma ya probada del adapter
        API."""
        raise NotImplementedError


__all__ = ["MantisReadAdapter"]
