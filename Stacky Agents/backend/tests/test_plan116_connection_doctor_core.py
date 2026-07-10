"""Plan 116 F0 — núcleo puro: catálogo de remediación + clasificadores (sin red, sin Flask)."""
from __future__ import annotations

import os
import socket
import ssl
import sys
import urllib.error
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import connection_doctor as cd

_KINDS = {"retry", "copy_command", "open_url", "goto_section", "none"}


def test_catalog_every_code_has_complete_remediation():
    for code in cd.CODES:
        entry = cd.REMEDIATIONS[code]
        assert entry["title"].strip()
        assert entry["cause"].strip()
        steps = entry["steps"]
        assert isinstance(steps, list) and len(steps) >= 2
        assert all(isinstance(s, str) and s.strip() for s in steps)
        action = entry["action"]
        assert action["kind"] in _KINDS
        if action["kind"] == "copy_command":
            assert "command" in action
        elif action["kind"] == "open_url":
            assert "url" in action
        elif action["kind"] == "goto_section":
            assert "section_id" in action


def test_classify_http_401_403_404_5xx_none():
    assert cd.classify_http_error(401, None) == "AUTH_401"
    assert cd.classify_http_error(403, None) == "FORBIDDEN_403"
    assert cd.classify_http_error(404, None) == "NOT_FOUND_404"
    assert cd.classify_http_error(500, None) == "HTTP_5XX"
    assert cd.classify_http_error(503, None) == "HTTP_5XX"
    assert cd.classify_http_error(None, TimeoutError()) == "TIMEOUT"


def test_classify_socket_gaierror_timeout_refused_ssl():
    assert cd.classify_socket_error(socket.gaierror()) == "DNS_FAIL"
    assert cd.classify_socket_error(TimeoutError()) == "TIMEOUT"
    assert cd.classify_socket_error(ConnectionRefusedError()) == "TCP_REFUSED"
    assert cd.classify_socket_error(ssl.SSLError()) == "TLS_ERROR"
    assert cd.classify_socket_error(ValueError("x")) == "UNKNOWN"


def test_classify_urlerror_unwraps_reason():
    err = urllib.error.URLError(socket.gaierror())
    assert cd.classify_socket_error(err) == "DNS_FAIL"


def test_build_result_attaches_remediation_and_formats():
    r = cd.build_result(target="server:x", target_label="X", group="servers",
                        status="fail", code="DNS_FAIL", fmt={"host": "srv01"})
    assert "srv01" in r["remediation"]["cause"]
    assert "{host}" not in r["remediation"]["cause"]


def test_build_result_unknown_code_never_raises():
    r = cd.build_result(target="t", target_label="T", group="tracker",
                        status="fail", code="NO_EXISTE")
    assert r["remediation"]["title"] == cd.REMEDIATIONS["UNKNOWN"]["title"]


def test_build_result_ok_has_no_remediation():
    r = cd.build_result(target="t", target_label="T", group="tracker", status="ok")
    assert r["remediation"] is None


def test_build_result_truncates_detail():
    r = cd.build_result(target="t", target_label="T", group="tracker",
                        status="fail", code="UNKNOWN", detail="x" * 1000)
    assert len(r["detail"]) <= 300


def test_build_result_missing_placeholder_safe():
    r = cd.build_result(target="t", target_label="T", group="tracker",
                        status="fail", code="AUTH_401", fmt={})
    assert "?" in r["remediation"]["action"].get("url", "?")  # placeholder seguro, no lanza
