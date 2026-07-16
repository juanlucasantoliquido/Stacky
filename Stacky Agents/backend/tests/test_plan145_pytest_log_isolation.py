"""Plan 145 F2 (V7) — aislar el logging de pytest: STACKY_TEST_MODE redirige el
FileHandler default a %TEMP%/stacky-test-logs/, nunca a backend/data/logs/.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.local_file_logging as lfl  # noqa: E402


def test_conftest_sets_test_mode():
    assert os.environ.get("STACKY_TEST_MODE")


def test_install_redirects_to_tmp_under_test_mode(monkeypatch):
    monkeypatch.setenv("STACKY_TEST_MODE", "1")
    root = logging.getLogger()
    before = set(root.handlers)
    lfl._installed = False
    lfl.install_file_log_handler()
    try:
        lg = logging.getLogger("test145.pytest_isolation")
        lg.warning("probe")
        for h in set(root.handlers) - before:
            h.flush()

        tmp_log = lfl._test_logs_dir() / f"stacky-{date.today():%Y-%m-%d}.log"
        prod_log = lfl.logs_dir() / f"stacky-{date.today():%Y-%m-%d}.log"
        assert tmp_log.exists()
        # No confirmamos ausencia absoluta de prod_log (puede preexistir de
        # corridas reales del server), solo que ESTA emisión fue a tmp.
        assert "probe" in tmp_log.read_text(encoding="utf-8")
    finally:
        for h in set(root.handlers) - before:
            root.removeHandler(h)
            h.close()
        lfl._installed = False


def test_explicit_base_dir_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_TEST_MODE", "1")
    root = logging.getLogger()
    before = set(root.handlers)
    lfl._installed = False
    lfl.install_file_log_handler(base_dir=tmp_path)
    try:
        lg = logging.getLogger("test145.pytest_isolation_explicit")
        lg.warning("probe2")
        for h in set(root.handlers) - before:
            h.flush()

        explicit_log = tmp_path / f"stacky-{date.today():%Y-%m-%d}.log"
        assert explicit_log.exists()
        assert "probe2" in explicit_log.read_text(encoding="utf-8")
    finally:
        for h in set(root.handlers) - before:
            root.removeHandler(h)
            h.close()
        lfl._installed = False
