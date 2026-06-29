"""Plan 74 F5 — Migración de attachments (descarga binaria + verificación hash).

C3: download_attachment_to_temp usa GET binario autenticado explícito.
PROHIBIDO reusar ado_client._request (devuelve dict/JSON, NO sirve para binarios).
"""
from __future__ import annotations

import base64
import hashlib
import os
import tempfile

import requests


def compute_sha256(file_path: str) -> str:
    """Calcula SHA-256 del archivo en file_path. Pura."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def download_attachment_to_temp(attachment_meta: dict, *, ado_pat: str) -> str:
    """Descarga el binario ADO a un temp file. Retorna la ruta temporal. NO sube nada.

    C3 — IMPLEMENTACIÓN EXPLÍCITA. PROHIBIDO reusar ado_client._request.
    El PAT ADO va como user vacío en Basic Auth.
    GET puro = read-only sobre el origen ADO.
    """
    url = attachment_meta.get("url") or attachment_meta.get("downloadUrl") or ""
    name = attachment_meta.get("name", "attach")
    suffix = "_" + name.replace("/", "_")

    auth = base64.b64encode(f":{ado_pat}".encode()).decode()
    with requests.get(
        url,
        headers={"Authorization": f"Basic {auth}"},
        stream=True,
        timeout=60,
    ) as r:
        r.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as fh:
            for chunk in r.iter_content(8192):
                fh.write(chunk)
        return path


def migrate_attachment(attachment_meta: dict, dest_provider, *, dest_iid: str, ado_pat: str) -> dict:
    """Flujo completo de un attachment:
    1. download_attachment_to_temp (GET binario ADO)
    2. compute_sha256(local)
    3. dest_provider.upload_attachment(temp_path, name)
    4. dest_provider.link_attachment(dest_iid, result)
    5. cleanup temp file (siempre, éxito o fallo)

    Retorna {name, local_sha256, dest_markdown, verified: bool}.
    """
    name = attachment_meta.get("name", "attach")
    tmp_path = None
    try:
        tmp_path = download_attachment_to_temp(attachment_meta, ado_pat=ado_pat)
        local_sha256 = compute_sha256(tmp_path)

        upload_result = dest_provider.upload_attachment(tmp_path, name)
        dest_markdown = (upload_result or {}).get("markdown", "")

        dest_provider.link_attachment(dest_iid, upload_result or {})

        return {
            "name": name,
            "local_sha256": local_sha256,
            "dest_markdown": dest_markdown,
            "verified": True,
        }
    except Exception as exc:
        return {
            "name": name,
            "local_sha256": "",
            "dest_markdown": "",
            "verified": False,
            "error": str(exc),
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
