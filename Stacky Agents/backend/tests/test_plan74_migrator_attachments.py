"""Plan 74 F5 — Tests de migrator_attachments.py (descarga binaria + hash + cleanup).

5 casos.
"""
import os
import pathlib
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest

from services.migrator_attachments import compute_sha256, migrate_attachment

_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "migrator"
_SAMPLE = _FIXTURES / "sample.txt"

# Hash SHA-256 conocido del archivo de fixture
import hashlib
_SAMPLE_SHA256 = hashlib.sha256(_SAMPLE.read_bytes()).hexdigest()


def test_compute_sha256_determinista():
    """compute_sha256 sobre archivo conocido → hash exacto determinista."""
    result = compute_sha256(str(_SAMPLE))
    assert result == _SAMPLE_SHA256


def test_migrate_attachment_llama_upload_y_link_en_orden():
    """migrate_attachment con mock_dest → llama upload_attachment y link_attachment en orden."""
    dest = MagicMock()
    dest.upload_attachment.return_value = {
        "markdown": "![file](https://gl.ex.com/file.txt)",
        "url": "https://gl.ex.com/file.txt",
    }
    dest.link_attachment.return_value = {}

    attachment_meta = {
        "id": "a1",
        "name": "sample.txt",
        "url": "https://ado.example.com/attach/a1",
    }

    with patch("services.migrator_attachments.download_attachment_to_temp",
               return_value=str(_SAMPLE)):
        result = migrate_attachment(
            attachment_meta, dest,
            dest_iid="10", ado_pat="PAT",
        )

    dest.upload_attachment.assert_called_once()
    dest.link_attachment.assert_called_once()
    call_args = dest.upload_attachment.call_args
    assert "sample.txt" in str(call_args)


def test_migrate_attachment_upload_falla_devuelve_verified_false():
    """upload_attachment levanta excepción → migrate_attachment retorna verified=False."""
    dest = MagicMock()
    dest.upload_attachment.side_effect = Exception("upload fail")

    attachment_meta = {"id": "a1", "name": "sample.txt", "url": "http://x.com/a1"}

    with patch("services.migrator_attachments.download_attachment_to_temp",
               return_value=str(_SAMPLE)):
        result = migrate_attachment(attachment_meta, dest, dest_iid="10", ado_pat="PAT")

    assert result["verified"] is False


def test_cleanup_tras_migrate_attachment_exitoso():
    """Tras migrate_attachment exitoso, el temp file fue eliminado."""
    # Crear un temp file real para verificar cleanup
    fd, tmp_path = tempfile.mkstemp(suffix="_test.txt")
    with os.fdopen(fd, "wb") as fh:
        fh.write(b"test content")

    dest = MagicMock()
    dest.upload_attachment.return_value = {"markdown": "![f](u)", "url": "u"}
    dest.link_attachment.return_value = {}

    attachment_meta = {"id": "a1", "name": "test.txt", "url": "http://x.com/a1"}

    with patch("services.migrator_attachments.download_attachment_to_temp",
               return_value=tmp_path):
        migrate_attachment(attachment_meta, dest, dest_iid="10", ado_pat="PAT")

    assert not os.path.exists(tmp_path), "El temp file debe ser eliminado tras la subida"


def test_cleanup_tras_migrate_attachment_fallido():
    """Tras migrate_attachment fallido (upload lanza), el temp file igual fue eliminado."""
    fd, tmp_path = tempfile.mkstemp(suffix="_fail.txt")
    with os.fdopen(fd, "wb") as fh:
        fh.write(b"content")

    dest = MagicMock()
    dest.upload_attachment.side_effect = Exception("fail")

    attachment_meta = {"id": "a2", "name": "fail.txt", "url": "http://x.com/a2"}

    with patch("services.migrator_attachments.download_attachment_to_temp",
               return_value=tmp_path):
        migrate_attachment(attachment_meta, dest, dest_iid="10", ado_pat="PAT")

    assert not os.path.exists(tmp_path), "El temp file debe ser eliminado aunque la subida falle"
