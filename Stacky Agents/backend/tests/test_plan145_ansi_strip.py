"""Plan 145 F1 — strip ANSI en el FileHandler diario y en el sink SystemLog/UI.

Elimina secuencias ANSI del archivo .log y del visor System Log (DB), sin
tocar el StreamHandler de consola (que conserva color).
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.local_file_logging as lfl  # noqa: E402
import services.console_log_handler as clh  # noqa: E402


def _make_record(msg: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="werkzeug",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


def test_formatter_strips_ansi():
    record = _make_record("\x1b[33mGET /x HTTP/1.1\x1b[0m")
    formatter = lfl._AnsiStrippingFormatter("%(message)s")
    out = formatter.format(record)
    assert "\x1b" not in out
    assert "GET /x HTTP/1.1" in out


def test_plain_formatter_keeps_ansi_when_disabled(monkeypatch):
    monkeypatch.setenv("STACKY_LOG_STRIP_ANSI", "false")
    assert lfl._strip_ansi_enabled() is False


def test_file_handler_writes_clean_line(tmp_path, monkeypatch):
    monkeypatch.delenv("STACKY_LOG_STRIP_ANSI", raising=False)
    root = logging.getLogger()
    before = set(root.handlers)
    lfl._installed = False
    lfl.install_file_log_handler(base_dir=tmp_path)
    try:
        werk = logging.getLogger("werkzeug")
        # WARNING (no INFO): el root logger por default está en WARNING y este
        # test no reconfigura logging global; WARNING atraviesa sin necesidad
        # de tocar niveles de logger (evita fugas de estado entre tests).
        werk.warning("\x1b[33mGET /api/health HTTP/1.1\x1b[0m 200")
        for h in set(root.handlers) - before:
            h.flush()
        from datetime import date

        log_path = tmp_path / f"stacky-{date.today():%Y-%m-%d}.log"
        content = log_path.read_text(encoding="utf-8")
        assert "\x1b" not in content
        assert "GET /api/health HTTP/1.1" in content
    finally:
        for h in set(root.handlers) - before:
            root.removeHandler(h)
            h.close()
        lfl._installed = False


def test_format_does_not_mutate_record():
    record = _make_record("\x1b[33mGET /x HTTP/1.1\x1b[0m")
    stripping = lfl._AnsiStrippingFormatter("%(message)s")
    plain = logging.Formatter("%(message)s")

    stripped_out = stripping.format(record)
    plain_out = plain.format(record)

    assert "\x1b" not in stripped_out
    assert "\x1b" in plain_out


def test_systemlog_handler_uses_stripping_formatter(monkeypatch):
    monkeypatch.delenv("STACKY_LOG_STRIP_ANSI", raising=False)
    root = logging.getLogger()
    before = set(root.handlers)
    clh._installed = False
    clh.install_console_log_handler()
    try:
        added = [h for h in root.handlers if h not in before]
        assert len(added) == 1
        assert isinstance(added[0].formatter, lfl._AnsiStrippingFormatter)
    finally:
        for h in set(root.handlers) - before:
            root.removeHandler(h)
        clh._installed = False
