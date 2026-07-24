"""tools/migrar_mantis_gitlab/adapters/api_adapter.py — Plan 217 F2a (después
del scraping, C6).

`MantisApiReadAdapter`: implementación de `MantisReadAdapter` que envuelve
una instancia real de `MantisClient` (REST) ya construida (inyección de
dependencia — la resolución de credenciales/protocolo desde
`migration_config.json` es responsabilidad del CLI/config_loader, fases
posteriores, fuera de este batch). Camino robusto para instancias Mantis
que sí tengan REST habilitado (a diferencia del scraping, F2b, que es el
único camino viable HOY contra `soporte.ais-int.net`).

Limitación declarada (no oculta, decisión explícita de este batch):
`MantisSOAPClient` (`services/mantis_client.py:751`) NO tiene métodos
equivalentes a `fetch_all_issues()`/`download_attachment_binary()` (solo
`fetch_open_issues` `:837` y `fetch_notes`). Agregarle esos métodos sin
evidencia de que son triviales/simétricos queda fuera de este batch. Por
eso este adapter soporta SOLO el camino REST (`MantisClient`); si se le
pasa un `MantisSOAPClient`, lanza `NotImplementedError` con mensaje claro
en vez de degradar en silencio con datos incompletos.
"""
from __future__ import annotations

from typing import Any

from services.mantis_client import MantisClient, MantisSOAPClient

from .base import MantisReadAdapter


class MantisApiReadAdapter(MantisReadAdapter):
    """Adapter de lectura Mantis vía REST (`MantisClient`), F2a."""

    def __init__(self, client: MantisClient) -> None:
        if isinstance(client, MantisSOAPClient):
            raise NotImplementedError(
                "MantisApiReadAdapter solo soporta el protocolo REST (MantisClient) "
                "en este batch (Plan 217 F2a): MantisSOAPClient no expone "
                "fetch_all_issues()/download_attachment_binary() equivalentes. "
                "Usá extraction_mode='scraping' (MantisWebScrapingReadAdapter) "
                "para instancias SOAP-only."
            )
        self._client = client

    # ── MantisReadAdapter ───────────────────────────────────────────────

    def fetch_all_issues(self) -> list[dict[str, Any]]:
        return self._client.fetch_all_issues()

    def fetch_comments(self, issue_id: int) -> list[dict[str, Any]]:
        return self._client.fetch_notes(issue_id)

    def fetch_attachments(self, issue_id: int) -> list[dict[str, Any]]:
        return self._client.fetch_attachments(issue_id)

    def fetch_relationships(self, issue_id: int) -> list[dict[str, Any]]:
        # `MantisClient` (REST) no expone en este batch un endpoint dedicado
        # a relaciones estructuradas (parent/child/related/duplicate) sobre
        # la instancia de referencia evaluada en el Plan 217. Se declara
        # explícitamente como no soportado (lista vacía), no se inventa un
        # dato — el reporte final (fases posteriores) debe reflejar el gap
        # si esta ruta se usa contra un origen que sí las expone.
        return []

    # ── Extensión no-abstracta (adjuntos binarios) ───────────────────────

    def download_attachment_binary(self, file_id: str | int) -> bytes:
        """No forma parte de `MantisReadAdapter`, pero se expone para que
        `migrator_mg_attachments.py` (F6, otro batch) pueda descargar
        binarios reales vía API cuando `extraction_mode` es `api`."""
        return self._client.download_attachment_binary(file_id)


__all__ = ["MantisApiReadAdapter"]
