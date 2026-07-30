"""tests/test_mg_attachments.py — Plan 217 Batch 4, F6a.

Valida `tools/migrar_mantis_gitlab/migrator_mg_attachments.py` con un
`origin_adapter` FAKE (implementa solo `download_attachment_binary`, que es
lo único que este módulo usa de la interfaz `MantisReadAdapter`) y un
`writer` FAKE:
  (a) descarga+sube+linkea OK — verifica `compute_sha256` calculado sobre
      el temp file ANTES de que se borre.
  (b) adjunto sobre el límite con `skip_if_over_limit=True` — no descarga
      (el origin_adapter fake NUNCA es invocado).
  (c) limpieza del temp file SIEMPRE, incluso si el upload falla.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from tools.migrar_mantis_gitlab.migrator_mg_attachments import (
    download_mg_attachment_to_temp,
    migrate_attachment_mg,
)

_CONTENT = b"contenido binario de prueba, no es texto real \x00\x01\x02"


class _FakeOriginAdapter:
    def __init__(self, *, content: bytes = _CONTENT, should_be_called: bool = True) -> None:
        self._content = content
        self.calls: list = []
        self._should_be_called = should_be_called

    def download_attachment_binary(self, file_id):
        self.calls.append(file_id)
        return self._content


class _FakeWriter:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.uploaded: list[tuple[str, str]] = []
        self.linked: list[tuple[str, dict]] = []
        self.last_upload_tmp_path_existed: "bool | None" = None
        self._fail_upload = fail_upload

    def upload_attachment(self, file_path, filename):
        self.last_upload_tmp_path_existed = os.path.exists(file_path)
        if self._fail_upload:
            raise RuntimeError("fallo simulado subiendo el adjunto")
        self.uploaded.append((file_path, filename))
        return {"url": f"/uploads/x/{filename}", "markdown": f"[{filename}](/uploads/x/{filename})"}

    def link_attachment(self, item_iid, attachment_meta):
        self.linked.append((item_iid, attachment_meta))
        return {"iid": item_iid}


# ── (a) descarga + sube + linkea OK ─────────────────────────────────────


def test_migrate_attachment_mg_ok_descarga_sube_y_linkea(monkeypatch):
    adapter = _FakeOriginAdapter()
    writer = _FakeWriter()
    # El `size` declarado tiene que coincidir con el contenido real: desde
    # que existe el gate anti-descarga-truncada, un meta inconsistente es
    # justamente lo que se quiere rechazar.
    attachment_meta = {"id": "501", "name": "captura.png",
                       "size": len(_CONTENT), "url": "https://mantis/x"}

    import tools.migrar_mantis_gitlab.migrator_mg_attachments as mg_attachments_module

    captured_paths: list[str] = []
    original_download = mg_attachments_module.download_mg_attachment_to_temp

    def _spy_download(meta, *, origin_adapter):
        path = original_download(meta, origin_adapter=origin_adapter)
        captured_paths.append(path)
        return path

    monkeypatch.setattr(mg_attachments_module, "download_mg_attachment_to_temp", _spy_download)

    result = mg_attachments_module.migrate_attachment_mg(
        attachment_meta, writer, adapter,
        dest_iid="99", max_size_mb=50, skip_if_over_limit=True,
    )

    assert result["skipped"] is False
    assert result["verified"] is True
    assert result["local_sha256"] == hashlib.sha256(_CONTENT).hexdigest()
    assert adapter.calls == ["501"]
    assert len(writer.uploaded) == 1
    assert writer.uploaded[0][1] == "captura.png"
    assert len(writer.linked) == 1
    assert writer.linked[0][0] == "99"
    # El temp file existía en el momento del upload (compute_sha256 se
    # calculó sobre un archivo real, no sobre bytes en memoria)...
    assert writer.last_upload_tmp_path_existed is True
    # ...pero ya no existe después: limpieza SIEMPRE (§15 punto 5 del plan).
    assert len(captured_paths) == 1
    assert not os.path.exists(captured_paths[0])


# ── (b) sobre el límite de tamaño: no descarga ──────────────────────────


def test_migrate_attachment_mg_sobre_limite_no_descarga():
    adapter = _FakeOriginAdapter()
    writer = _FakeWriter()
    # 100 MB declarados, límite configurado en 50 MB.
    attachment_meta = {"id": "999", "name": "video.mp4", "size": 100 * 1024 * 1024, "url": "https://mantis/y"}

    result = migrate_attachment_mg(
        attachment_meta, writer, adapter,
        dest_iid="99", max_size_mb=50, skip_if_over_limit=True,
    )

    assert result["skipped"] is True
    assert result["reason"] == "over_size_limit"
    assert result["original_url"] == "https://mantis/y"
    # Nunca se descargó (el origin_adapter no fue invocado).
    assert adapter.calls == []
    assert writer.uploaded == []
    assert writer.linked == []


# ── (c) limpieza del temp file SIEMPRE, incluso si el upload falla ──────


def test_migrate_attachment_mg_borra_temp_file_tras_fallo_de_upload(monkeypatch):
    adapter = _FakeOriginAdapter()
    writer = _FakeWriter(fail_upload=True)
    attachment_meta = {"id": "501", "name": "captura.png", "size": 1024, "url": "https://mantis/x"}

    captured_paths: list[str] = []
    original_download = download_mg_attachment_to_temp

    def _spy_download(meta, *, origin_adapter):
        path = original_download(meta, origin_adapter=origin_adapter)
        captured_paths.append(path)
        return path

    import tools.migrar_mantis_gitlab.migrator_mg_attachments as mg_attachments_module

    monkeypatch.setattr(mg_attachments_module, "download_mg_attachment_to_temp", _spy_download)

    result = mg_attachments_module.migrate_attachment_mg(
        attachment_meta, writer, adapter,
        dest_iid="99", max_size_mb=50, skip_if_over_limit=True,
    )

    assert result["verified"] is False
    assert len(captured_paths) == 1
    assert not os.path.exists(captured_paths[0]), "El temp file debe eliminarse SIEMPRE, incluso si falla el upload"


# ── download_mg_attachment_to_temp aislado ──────────────────────────────


def test_download_mg_attachment_to_temp_devuelve_ruta_con_contenido_correcto():
    adapter = _FakeOriginAdapter()
    attachment_meta = {"id": "777", "name": "log de prueba.txt"}

    path = download_mg_attachment_to_temp(attachment_meta, origin_adapter=adapter)
    try:
        assert os.path.exists(path)
        with open(path, "rb") as fh:
            assert fh.read() == _CONTENT
        assert adapter.calls == ["777"]
    finally:
        os.unlink(path)


# ── Gates anti-adjunto-fantasma (regresión Ripley 2026-07-29) ───────────
#
# La descarga de Mantis devolvía 0 bytes (URL sin `type=bug` -> HTTP 400 con
# cuerpo vacío) y el flujo subía ESE vacío a GitLab reportando `verified:
# True`. Resultado real: 167 uploads de 0 bytes en el proyecto destino, todos
# dados por migrados. Estos dos gates lo hacen imposible.


class _AdapterQueDevuelveVacio:
    def download_attachment_binary(self, file_id):
        return b""


def test_migrate_attachment_mg_rechaza_descarga_vacia():
    writer = _FakeWriter()
    meta = {"id": "501", "name": "captura.png", "size": 0, "url": "https://mantis/x"}

    result = migrate_attachment_mg(
        meta, writer, _AdapterQueDevuelveVacio(),
        dest_iid="99", max_size_mb=50, skip_if_over_limit=True,
    )

    assert result["verified"] is False
    assert "VACÍO" in result["error"] or "0 bytes" in result["error"]
    assert writer.uploaded == [], "nunca debe subirse un adjunto vacío"
    assert writer.linked == []


def test_migrate_attachment_mg_rechaza_descarga_truncada():
    """Mantis declara N bytes y se bajan menos: descarga cortada."""
    writer = _FakeWriter()
    meta = {"id": "501", "name": "informe.pdf",
            "size": len(_CONTENT) + 5000, "url": "https://mantis/x"}

    result = migrate_attachment_mg(
        meta, writer, _FakeOriginAdapter(),
        dest_iid="99", max_size_mb=50, skip_if_over_limit=True,
    )

    assert result["verified"] is False
    assert "incompleto" in result["error"]
    assert writer.uploaded == []


def test_migrate_attachment_mg_propaga_el_marker_al_link():
    """El marker tiene que llegar al `link_attachment`: es lo que hace
    idempotente la corrida siguiente."""
    writer = _FakeWriter()
    meta = {"id": "501", "name": "captura.png", "size": len(_CONTENT)}
    marker = "<!-- stacky-migrated:mantis-file:310:26020:501 -->"

    result = migrate_attachment_mg(
        meta, writer, _FakeOriginAdapter(),
        dest_iid="99", max_size_mb=50, skip_if_over_limit=True, marker=marker,
    )

    assert result["verified"] is True
    assert writer.linked[0][1]["marker"] == marker
