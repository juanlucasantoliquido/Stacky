"""Tests de clasificación de errores."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestClassifyException:
    def test_http_401_es_auth(self):
        from error_classifier import classify_exception
        exc = urllib.error.HTTPError(
            url="https://api.example.com/foo",
            code=401, msg="Unauthorized", hdrs=None, fp=None,
        )
        assert classify_exception(exc) == "auth"

    def test_http_403_es_auth(self):
        from error_classifier import classify_exception
        exc = urllib.error.HTTPError(
            url="https://api.example.com/foo",
            code=403, msg="Forbidden", hdrs=None, fp=None,
        )
        assert classify_exception(exc) == "auth"

    def test_url_error_es_network(self):
        from error_classifier import classify_exception
        exc = urllib.error.URLError("Connection refused")
        assert classify_exception(exc) == "network"

    def test_socket_timeout_es_network(self):
        from error_classifier import classify_exception
        exc = socket.timeout("timed out")
        assert classify_exception(exc) == "network"

    def test_connection_refused_es_network(self):
        from error_classifier import classify_exception
        exc = ConnectionRefusedError("nope")
        assert classify_exception(exc) == "network"

    def test_subprocess_error_es_technical(self):
        from error_classifier import classify_exception
        exc = subprocess.CalledProcessError(returncode=1, cmd="svn")
        assert classify_exception(exc) == "technical"

    def test_file_not_found_dentro_del_ticket_es_functional(self, tmp_path):
        from error_classifier import classify_exception
        ticket_folder = tmp_path / "asignada" / "0099999"
        ticket_folder.mkdir(parents=True)
        missing = ticket_folder / "DEV_COMPLETADO.md"
        exc = FileNotFoundError(2, "No such file", str(missing))
        assert classify_exception(exc, ticket_folder=str(ticket_folder)) == "functional"

    def test_file_not_found_fuera_del_ticket_es_technical(self, tmp_path):
        from error_classifier import classify_exception
        outside = tmp_path / "other.txt"
        exc = FileNotFoundError(2, "No such file", str(outside))
        ticket_folder = tmp_path / "asignada" / "0099999"
        ticket_folder.mkdir(parents=True)
        assert classify_exception(exc, ticket_folder=str(ticket_folder)) == "technical"

    def test_permission_error_es_user(self):
        from error_classifier import classify_exception
        exc = PermissionError("denied")
        assert classify_exception(exc) == "user"

    def test_pydantic_validation_error_es_data(self):
        from error_classifier import classify_exception
        try:
            from pydantic import BaseModel
        except ImportError:  # pragma: no cover
            pytest.skip("pydantic no disponible")

        class M(BaseModel):
            x: int

        try:
            M(x="no-int")  # type: ignore[arg-type]
        except Exception as e:
            assert classify_exception(e) == "data"
        else:
            pytest.fail("Se esperaba ValidationError")

    def test_exception_generica_es_technical(self):
        from error_classifier import classify_exception
        assert classify_exception(RuntimeError("boom")) == "technical"


class TestFriendlyMessage:
    def test_mensaje_auth_menciona_servicio(self):
        from error_classifier import friendly_message
        exc = urllib.error.HTTPError(
            url="https://dev.azure.com/org/_apis/wit",
            code=401, msg="Unauthorized", hdrs=None, fp=None,
        )
        msg = friendly_message(exc)
        assert "autenticación" in msg.lower()
        assert "dev.azure.com" in msg

    def test_mensaje_network_sin_servicio_usa_default(self):
        from error_classifier import friendly_message
        exc = ConnectionRefusedError("nope")
        msg = friendly_message(exc)
        assert "conectividad" in msg.lower() or "contactar" in msg.lower()

    def test_mensaje_functional_menciona_archivo(self, tmp_path):
        from error_classifier import friendly_message
        ticket_folder = tmp_path / "asignada" / "0099999"
        ticket_folder.mkdir(parents=True)
        missing = ticket_folder / "missing.md"
        exc = FileNotFoundError(2, "No such file", str(missing))
        msg = friendly_message(exc, ticket_folder=str(ticket_folder))
        assert "archivo" in msg.lower() or "missing" in msg.lower()
