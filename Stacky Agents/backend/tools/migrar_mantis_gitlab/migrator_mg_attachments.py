"""tools/migrar_mantis_gitlab/migrator_mg_attachments.py — Plan 217 Batch 4, F6a.

Descarga binaria de adjuntos Mantis + subida a GitLab. Reusa SOLO
`compute_sha256` (PURA) de `services/migrator_attachments.py:16` — el resto
de ese módulo (`download_attachment_to_temp`, firma `(attachment_meta, *,
ado_pat)`) es ADO-only y NO sirve acá (C7 del Plan 217: el origen Mantis
requiere cookie de sesión, no un PAT en Basic Auth).

Descarga polimórfica (decisión de diseño de este batch, ver docstring de
`adapters.base.MantisReadAdapter.download_attachment_binary`): en vez de
`isinstance(origin_adapter, MantisApiReadAdapter | MantisWebScrapingReadAdapter)`,
`download_attachment_binary(file_id)` se promovió a método ABSTRACTO de
`MantisReadAdapter` e implementado por AMBOS adapters concretos — este
módulo llama al método de la interfaz, sin conocer de qué adapter concreto
se trata. Más limpio, y consistente con el resto de `MantisReadAdapter`
(ya polimórfico para fetch_all_issues/fetch_comments/etc.).

Limpieza del temp file SIEMPRE (try/finally), éxito o fallo — mismo
principio que `services.migrator_attachments.migrate_attachment` y
exigencia dura de §15 punto 5 del Plan 217 (datos personales: "eliminarse
inmediatamente después de subirse")."""
from __future__ import annotations

import os
import tempfile

from services.migrator_attachments import compute_sha256

from .destination_writer import DestinationWriter


def download_mg_attachment_to_temp(attachment_meta: dict, *, origin_adapter) -> str:
    """Descarga el binario del adjunto Mantis a un archivo temporal vía
    `origin_adapter.download_attachment_binary(file_id)` (polimorfismo, ver
    docstring del módulo). Devuelve la ruta del temp file — NO sube nada."""
    file_id = attachment_meta.get("id")
    name = attachment_meta.get("name") or "attachment"
    content = origin_adapter.download_attachment_binary(file_id)

    suffix = "_" + name.replace("/", "_").replace("\\", "_")
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    return path


def _over_size_limit_result(attachment_meta: dict, *, size: int, max_size_mb: int) -> dict:
    return {
        "name": attachment_meta.get("name", "attach"),
        "skipped": True,
        "reason": "over_size_limit",
        "size": size,
        "max_size_mb": max_size_mb,
        "original_url": attachment_meta.get("url", ""),
    }


def migrate_attachment_mg(
    attachment_meta: dict,
    writer: DestinationWriter,
    origin_adapter,
    *,
    dest_iid: str,
    max_size_mb: int,
    skip_if_over_limit: bool,
    marker: str = "",
) -> dict:
    """Flujo completo de un adjunto Mantis -> GitLab (mismo patrón que
    `services.migrator_attachments.migrate_attachment`, Plan 74 F5,
    adaptado a origen Mantis):

    1. Chequeo de tamaño ANTES de descargar, si `attachment_meta["size"]`
       ya lo trae (§6 del plan: adjuntos sobre el límite "se registran
       como advertencia... link directo al adjunto original", nunca abortan
       la corrida) — evita una descarga inútil de un archivo que se va a
       saltear igual.
    2. `download_mg_attachment_to_temp` (GET binario, API o scraping según
       el adapter recibido).
    3. Re-chequeo de tamaño REAL post-descarga (por si el metadato de
       Mantis faltaba o era incorrecto): nunca se sube un archivo fuera de
       límite solo porque el tamaño declarado era engañoso.
    4. `compute_sha256` del temp file (reuso puro).
    5. `writer.upload_attachment` + `writer.link_attachment`.
    6. Limpieza del temp file SIEMPRE (try/finally), éxito o fallo.
    """
    name = attachment_meta.get("name", "attach")
    declared_size = attachment_meta.get("size")
    max_size_bytes = max_size_mb * 1024 * 1024

    if declared_size is not None and declared_size > max_size_bytes and skip_if_over_limit:
        return _over_size_limit_result(attachment_meta, size=declared_size, max_size_mb=max_size_mb)

    tmp_path = None
    try:
        tmp_path = download_mg_attachment_to_temp(attachment_meta, origin_adapter=origin_adapter)

        real_size = os.path.getsize(tmp_path)
        if real_size > max_size_bytes and skip_if_over_limit:
            return _over_size_limit_result(attachment_meta, size=real_size, max_size_mb=max_size_mb)

        # Un adjunto de 0 bytes casi nunca es real: es la firma de una
        # descarga fallida que devolvió cuerpo vacío. Subirlo y darlo por
        # migrado es peor que fallar, porque el issue queda con un archivo
        # que parece estar y no está.
        if real_size == 0:
            raise RuntimeError(
                f"el adjunto {name!r} se descargó VACÍO (0 bytes) desde Mantis; "
                "no se sube."
            )
        # Si Mantis declaró un tamaño, tiene que coincidir: una descarga
        # truncada (sesión caída a mitad, proxy que corta) no puede pasar
        # como buena.
        if declared_size and real_size != declared_size:
            raise RuntimeError(
                f"el adjunto {name!r} se descargó incompleto: Mantis declara "
                f"{declared_size} bytes y se bajaron {real_size}."
            )

        local_sha256 = compute_sha256(tmp_path)

        upload_result = writer.upload_attachment(tmp_path, name)
        # El marker viaja DENTRO del meta para no romper la firma
        # `link_attachment(item_iid, attachment_meta)` que comparten las 3
        # implementaciones de `DestinationWriter`. Es lo que hace detectable
        # este adjunto en una corrida futura (idempotencia).
        meta_link = dict(upload_result or {})
        if marker:
            meta_link["marker"] = marker
        writer.link_attachment(dest_iid, meta_link)

        return {
            "name": name,
            "skipped": False,
            "local_sha256": local_sha256,
            "dest": upload_result or {},
            "verified": True,
        }
    except Exception as exc:
        return {
            "name": name,
            "skipped": False,
            "verified": False,
            "error": str(exc),
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


__all__ = ["download_mg_attachment_to_temp", "migrate_attachment_mg"]
