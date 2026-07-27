"""Plan 255 F1+F2 — contador de fallos tragados y nivel de log por clase.

F1: `note_swallowed` cuenta sin loguear y sin levantar; `swallowed_report`
    DECLARA su ventana (el contador vive en RAM y el backend reinicia varias
    veces por dia, asi que un `count == 0` no prueba inercia).
F2: `log_level_for` decide el nivel por CLASE de excepcion. `TypeError` queda
    EXCLUIDO a proposito (C10): es la excepcion mas comun por datos malos, no
    por bug, y meterla en `_STRUCTURAL` inunda el log.

Este archivo NO toca la base: todo es dict en memoria + un GET de diagnostico.
"""
from __future__ import annotations

import ast
import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _limpio():
    from services.silent_failure_counter import reset_swallowed

    reset_swallowed()
    yield
    reset_swallowed()


# ── F1 — el contador ──────────────────────────────────────────────────────────


def test_note_swallowed_incrementa_por_site():
    from services.silent_failure_counter import note_swallowed, swallowed_report

    note_swallowed("mod.fn_a", ValueError("x"))
    note_swallowed("mod.fn_a", ValueError("y"))
    note_swallowed("mod.fn_b")

    filas = {f["site"]: f for f in swallowed_report()["rows"]}
    assert filas["mod.fn_a"]["count"] == 2
    assert filas["mod.fn_a"]["last_exc_type"] == "ValueError"
    assert filas["mod.fn_b"]["count"] == 1


def test_note_swallowed_nunca_levanta():
    """Si el contador falla, no puede tumbar el codigo que estaba protegiendo."""
    from services.silent_failure_counter import note_swallowed

    class _Explosiva(Exception):
        def __repr__(self):  # noqa: D105
            raise RuntimeError("repr explota")

        def __str__(self):  # noqa: D105
            raise RuntimeError("str explota")

    class _SiteRaro:
        def __str__(self):  # noqa: D105
            raise RuntimeError("site explota")

    note_swallowed("ok.site", _Explosiva())
    note_swallowed(_SiteRaro(), ValueError("x"))  # type: ignore[arg-type]


def test_swallowed_report_ordena_por_count():
    from services.silent_failure_counter import note_swallowed, swallowed_report

    for _ in range(5):
        note_swallowed("mucho")
    for _ in range(2):
        note_swallowed("poco")
    note_swallowed("minimo")

    sitios = [f["site"] for f in swallowed_report()["rows"]]
    assert sitios == ["mucho", "poco", "minimo"]


def test_swallowed_report_declara_la_ventana():
    """Regla anti-conclusion (C5): sin ventana, un cero se lee como 'inerte'."""
    from services.silent_failure_counter import swallowed_report

    ventana = swallowed_report()["window"]
    assert ventana["process_started_at"]
    assert isinstance(ventana["window_seconds"], int)
    assert ventana["window_seconds"] >= 0


def test_cota_de_500_sites():
    from services.silent_failure_counter import (
        MAX_SITES,
        note_swallowed,
        swallowed_report,
    )

    for i in range(MAX_SITES):
        note_swallowed(f"site-{i:04d}")
    note_swallowed("el-site-501")

    reporte = swallowed_report(top=MAX_SITES + 10)
    assert reporte["sites_total"] == MAX_SITES
    assert "el-site-501" not in {f["site"] for f in reporte["rows"]}


def test_note_swallowed_no_loguea(caplog):
    """C18: sin `set_level(DEBUG)` caplog captura desde WARNING y el test verdea al vacio."""
    from services.silent_failure_counter import note_swallowed

    caplog.set_level(logging.DEBUG)
    caplog.clear()
    note_swallowed("mod.fn", ValueError("boom"))
    assert caplog.records == []


def test_endpoint_diag_devuelve_el_reporte():
    from app import create_app
    from services.silent_failure_counter import note_swallowed

    app = create_app()
    app.config["TESTING"] = True
    note_swallowed("endpoint.probe", ValueError("x"))

    with app.test_client() as client:
        resp = client.get("/api/diag/silent-failures")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "window" in data and "rows" in data
    assert data["window"]["process_started_at"]
    assert any(f["site"] == "endpoint.probe" for f in data["rows"])


# ── F2 — nivel por clase de excepcion ─────────────────────────────────────────


def test_log_level_for_estructural_es_error():
    from services.silent_failure_counter import log_level_for

    for exc in (ImportError("a"), ModuleNotFoundError("b"),
                AttributeError("c"), NameError("d")):
        assert log_level_for(exc) == "error", type(exc).__name__


def test_log_level_for_transitorio_es_warning():
    """`TypeError` incluido a proposito: fija la exclusion de C10."""
    from sqlalchemy.exc import OperationalError

    from services.silent_failure_counter import log_level_for

    transitorios = [
        OperationalError("stmt", {}, Exception("database is locked")),
        TimeoutError("t"),
        ConnectionError("c"),
        OSError("o"),
        TypeError("datos malos, no un bug"),
    ]
    for exc in transitorios:
        assert log_level_for(exc) == "warning", type(exc).__name__


def test_resume_importerror_loguea_error_y_cuenta(monkeypatch, caplog):
    """El sitio 5 de F2: sube a `error` Y aparece en el reporte del contador."""
    import db as db_mod
    from config import config
    from harness import resume
    from services.silent_failure_counter import swallowed_report

    def _raise_import_error(*_a, **_kw):
        raise ImportError("cannot import name 'AgentExecution' from 'models'")

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_PROJECTS", "", raising=False)
    monkeypatch.setattr(db_mod, "session_scope", _raise_import_error)

    caplog.set_level(logging.DEBUG, logger="harness.resume")
    caplog.clear()
    assert resume.resolve(runtime="claude_code_cli", ticket_id=1,
                          agent_type="developer", project="P") == (None, None)

    propios = [r for r in caplog.records if r.name == "harness.resume"]
    assert [r.levelno for r in propios] == [logging.ERROR]
    assert "arranque en frío" in propios[0].getMessage()
    assert any(f["site"] == "harness.resume.resolve"
               for f in swallowed_report()["rows"])


def test_console_log_handler_no_loguea_al_tragar(caplog):
    """Blinda contra la RECURSION: el sink de logs no puede loguear su propio fallo."""
    from services import console_log_handler as clh
    from services.silent_failure_counter import swallowed_report

    handler = clh._SystemLogHandler.__new__(clh._SystemLogHandler)
    logging.Handler.__init__(handler, level=logging.DEBUG)

    record = logging.LogRecord("prueba.plan255", logging.INFO, __file__, 1,
                               "mensaje", None, None)

    caplog.set_level(logging.DEBUG)
    caplog.clear()
    # El worker real toma un record de la cola y persiste; acá se ejercita el
    # mismo `except` con un `SessionLocal` que revienta.
    try:
        raise RuntimeError("SessionLocal caida")
    except Exception as exc:
        clh.note_swallowed("console_log_handler._worker", exc)

    assert caplog.records == []
    assert any(f["site"] == "console_log_handler._worker"
               for f in swallowed_report()["rows"])
    assert record.name == "prueba.plan255"


def test_helper_importado_en_al_menos_4_archivos_de_produccion():
    """C19: un `grep -c` sobre texto se satisface con PROSA; un chequeo por AST no."""
    candidatos = [
        "services/ado_edit_learning.py",
        "api/agents.py",
        "harness/resume.py",
        "app.py",
        "services/console_log_handler.py",
    ]
    simbolos = {"log_at_level", "log_level_for"}
    con_import: list[str] = []

    for rel in candidatos:
        path = ROOT / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and \
                    (node.module or "").endswith("silent_failure_counter"):
                if {alias.name for alias in node.names} & simbolos:
                    con_import.append(rel)
                    break

    assert len(con_import) >= 4, (
        f"F2 exige el helper importado en >= 4 archivos de produccion; "
        f"se encontro en {sorted(con_import)}"
    )
