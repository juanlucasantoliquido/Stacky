"""Plan 257 F0 — throttle de firmas, flush determinista y rotacion/purga real.

Cubre F1 (filtro en los TRES sumideros del root logger), F1-ter (flush
determinista: ninguna repeticion silenciada queda sin contabilizar), F1-bis
(los 5 call-sites de `log_throttled` en produccion, verificados con AST) y
F2 (rotacion por tamano + purga que corre de verdad).

Correr POR ARCHIVO (la suite completa contamina; gotcha conocido del repo):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan257_log_antirruido.py -v

Cero DB a proposito: todo lo que se ejercita aca es logging + filesystem
temporal, asi que el shared-cache in-memory de pytest no puede volverlo flaky.
"""
from __future__ import annotations

import ast
import logging
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import services.local_file_logging as lfl  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]

# El resumen se emite con este prefijo ASCII puro (C17): sin "x" de multiplicar
# (cp437 no lo tiene) y sin "%" (el template todavia no fue formateado).
_XN_RE = re.compile(r"\[x(\d+) repeticiones")


# ── infraestructura ─────────────────────────────────────────────────────────


class _Sink(logging.Handler):
    """Handler de prueba: guarda los records que SUPERAN sus filtros."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def handler_limpio():
    """Reset REAL del singleton: el guard `if _installed: return` convierte una
    segunda instalacion en no-op y hace que los tests de purga pasen o fallen
    segun el ORDEN de la suite."""
    root = logging.getLogger()
    previos = list(root.handlers)
    lfl._installed = False
    yield
    for h in list(root.handlers):
        if h not in previos:
            root.removeHandler(h)
            h.close()
    lfl._installed = False


@pytest.fixture
def logger_aislado():
    """Logger propio con propagate=False: no toca el root ni la consola."""
    lg = logging.getLogger("test257.aislado")
    previos = list(lg.handlers)
    lg.handlers = []
    lg.propagate = False
    lg.setLevel(logging.DEBUG)
    yield lg
    lg.handlers = previos
    lg.propagate = True


def _filtro(window_s: float = 60.0, max_sigs: int = 1000):
    return lfl._ThrottleFilter(window_s=window_s, max_sigs=max_sigs)


def _cablear(lg: logging.Logger, flt, n_sinks: int = 1) -> list[_Sink]:
    sinks = [_Sink() for _ in range(n_sinks)]
    for s in sinks:
        s.addFilter(flt)
        lg.addHandler(s)
    return sinks


def _record(msg: str, *, level: int = logging.WARNING, name: str = "test257.rec"):
    return logging.LogRecord(name, level, __file__, 1, msg, None, None)


# ── F1 — el filtro en los TRES sumideros ────────────────────────────────────


def test_throttle_emite_la_primera_y_silencia_las_repeticiones(logger_aislado):
    flt = _filtro()
    sink = _cablear(logger_aislado, flt)[0]

    for _ in range(100):
        logger_aislado.warning("misma firma repetida")

    assert len(sink.records) == 1


def test_throttle_emite_resumen_con_conteo_al_reaparecer(logger_aislado, monkeypatch):
    reloj = {"t": 1000.0}
    monkeypatch.setattr(lfl.time, "time", lambda: reloj["t"])
    flt = _filtro(window_s=60.0)
    sink = _cablear(logger_aislado, flt)[0]

    for _ in range(100):                       # 1 pasa + 99 silenciadas
        logger_aislado.warning("firma con piggyback")
    reloj["t"] += 120.0                        # ventana vencida
    logger_aislado.warning("firma con piggyback")

    assert len(sink.records) == 2
    assert "[x99 repeticiones en 60s] " in sink.records[1].msg


def test_throttle_no_afecta_firmas_distintas(logger_aislado):
    flt = _filtro()
    sink = _cablear(logger_aislado, flt)[0]

    logger_aislado.warning("firma alfa")
    logger_aislado.warning("firma beta")
    logger_aislado.warning("firma gamma")

    assert len(sink.records) == 3


def test_throttle_nunca_silencia_error_ni_critical(logger_aislado):
    flt = _filtro()
    sink = _cablear(logger_aislado, flt)[0]

    for _ in range(100):
        logger_aislado.error("un error estructural en loop")
    for _ in range(10):
        logger_aislado.critical("critico")

    assert len([r for r in sink.records if r.levelno == logging.ERROR]) == 100
    assert len([r for r in sink.records if r.levelno == logging.CRITICAL]) == 10


def test_firma_distingue_niveles():
    """C3 — normalizar el `levelno` colapsaba WARNING con INFO."""
    info = _record("mismo template", level=logging.INFO)
    warn = _record("mismo template", level=logging.WARNING)

    assert lfl._log_signature(info) != lfl._log_signature(warn)


def test_throttle_cota_de_memoria(logger_aislado):
    flt = _filtro(max_sigs=50)
    sink = _cablear(logger_aislado, flt)[0]

    for i in range(2000):
        logger_aislado.warning("firma unica %s-fin" % ("a" * (i % 7) + chr(65 + i % 26) + str(i)))

    assert len(flt._sigs) <= 50
    # Fail-open: las excedentes PASAN (preferimos ruido a silencio).
    assert len(sink.records) > 50


def test_firma_normaliza_numeros_y_rutas():
    a = lfl._log_signature(_record(r"ticket 123 en C:\a"))
    b = lfl._log_signature(_record(r"ticket 456 en C:\b"))
    assert a == b

    unc_a = lfl._log_signature(_record(r"copiando \\srv\share\x1"))
    unc_b = lfl._log_signature(_record(r"copiando \\otro\share\x2"))
    assert unc_a == unc_b

    posix_a = lfl._log_signature(_record("leyendo /var/log/x1"))
    posix_b = lfl._log_signature(_record("leyendo /var/log/x2"))
    assert posix_a == posix_b


def test_una_sola_instancia_en_todos_los_handlers_no_cuenta_de_mas(logger_aislado):
    """C4 — 3 handlers con la MISMA instancia: 10 repeticiones => 9 suprimidas."""
    flt = _filtro()
    sinks = _cablear(logger_aislado, flt, n_sinks=3)

    for _ in range(10):
        logger_aislado.warning("firma en tres sumideros")

    fila = flt.snapshot()[0]
    assert fila["suppressed"] == 9
    assert fila["count"] == 10
    for s in sinks:
        assert len(s.records) == 1


# ── F1-ter — flush determinista (cero perdida) ──────────────────────────────


def test_flush_emite_el_conteo_aunque_la_firma_no_vuelva(logger_aislado):
    flt = _filtro()
    sink = _cablear(logger_aislado, flt)[0]

    for _ in range(100):                       # 1 pasa + 99 silenciadas
        logger_aislado.warning("firma que nunca vuelve")

    emitidas = flt.flush_pending("test")

    assert emitidas == 1
    assert len(sink.records) == 2
    assert "[x99 repeticiones en 60s] " in sink.records[1].msg


def test_flush_no_emite_nada_sin_pendientes(logger_aislado):
    flt = _filtro()
    sink = _cablear(logger_aislado, flt)[0]

    logger_aislado.warning("una sola vez")

    assert flt.flush_pending("test") == 0
    assert len(sink.records) == 1


def test_flush_resetea_el_contador_y_no_duplica(logger_aislado):
    flt = _filtro()
    _cablear(logger_aislado, flt)

    for _ in range(20):
        logger_aislado.warning("firma para doble flush")

    assert flt.flush_pending("primero") == 1
    assert flt.flush_pending("segundo") == 0


def test_snapshot_no_resetea(logger_aislado):
    flt = _filtro()
    _cablear(logger_aislado, flt)

    for _ in range(5):
        logger_aislado.warning("firma para snapshot")

    primero = flt.snapshot()
    segundo = flt.snapshot()
    assert primero[0]["suppressed"] == segundo[0]["suppressed"] == 4


def test_invariante_cero_perdida(logger_aislado):
    """`sum(xN emitidos) + pendientes del snapshot == suprimidas totales`."""
    flt = _filtro()
    sink = _cablear(logger_aislado, flt)[0]

    # Bloque 1: UN solo template => 1 firma, 1 emitida + 499 silenciadas.
    for i in range(500):
        logger_aislado.warning("firma numero %s del invariante", i % 3)
    # Bloque 2: TRES templates distintos => 3 firmas, 3 emitidas + 497 silenciadas.
    for i in range(500):
        logger_aislado.warning(["alfa %s", "beta %s", "gamma %s"][i % 3], i)

    flt.flush_pending("invariante")

    emitidos = sum(int(m.group(1)) for r in sink.records
                   for m in [_XN_RE.search(str(r.msg))] if m)
    pendientes = sum(f["suppressed"] for f in flt.snapshot())
    suprimidas = sum(f["count"] for f in flt.snapshot()) - len(flt.snapshot())

    assert emitidos + pendientes == suprimidas
    assert suprimidas == (500 - 1) + (500 - 3)


# ── F1-bis — `log_throttled` cableado en produccion (AST, no grep) ──────────


_SITIOS = (
    "services/ado_edit_learning.py",
    "app.py",
    "api/tickets.py",
    "harness/resume.py",
    "services/output_watcher.py",
)


def _llamadas_log_throttled(path: Path) -> list[ast.Call]:
    arbol = ast.parse(path.read_text(encoding="utf-8"))
    salida: list[ast.Call] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        func = nodo.func
        nombre = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if nombre == "log_throttled":
            salida.append(nodo)
    return salida


def test_los_5_sitios_usan_log_throttled():
    faltan = []
    for rel in _SITIOS:
        llamadas = _llamadas_log_throttled(BACKEND / rel)
        validas = [c for c in llamadas if len(c.args) >= 4]
        if not validas:
            faltan.append(rel)
    assert faltan == [], f"sitios sin una llamada valida a log_throttled: {faltan}"


def test_log_throttled_tiene_call_sites_en_produccion():
    total = 0
    for rel in _SITIOS:
        total += len([c for c in _llamadas_log_throttled(BACKEND / rel) if len(c.args) >= 4])
    assert total >= 5, f"solo {total} call-sites validos de log_throttled"


def test_config_agents_dir_sigue_usando_log_state_change():
    """Guardia anti-regresion de C10: el dedup por ESTADO no se degrada."""
    src = (BACKEND / "config.py").read_text(encoding="utf-8")
    assert "log_state_change(" in src
    assert "log_throttled(" not in src


# ── F2 — rotacion por tamano y purga que corre de verdad ────────────────────


def _flags_rotacion(monkeypatch, *, max_bytes: int, max_parts: int = 10,
                    enabled: bool = True) -> None:
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_LOG_SIZE_ROTATION_ENABLED", enabled, raising=False)
    monkeypatch.setattr(cfg, "STACKY_LOG_MAX_BYTES", max_bytes, raising=False)
    monkeypatch.setattr(cfg, "STACKY_LOG_MAX_PARTS_PER_DAY", max_parts, raising=False)


def _handler_de_archivo(tmp_path: Path) -> lfl._DailyStackyFileHandler:
    h = lfl._DailyStackyFileHandler(tmp_path)
    h.setFormatter(logging.Formatter("%(message)s"))
    return h


def test_rotacion_por_tamano_abre_archivo_nuevo(tmp_path, monkeypatch):
    _flags_rotacion(monkeypatch, max_bytes=1024)
    h = _handler_de_archivo(tmp_path)
    try:
        for _ in range(40):
            h.emit(_record("x" * 100))
    finally:
        h.close()

    hoy = f"{date.today():%Y-%m-%d}"
    assert (tmp_path / f"stacky-{hoy}.log").exists()
    assert (tmp_path / f"stacky-{hoy}.1.log").exists()


def test_rotacion_respeta_max_parts_y_no_deja_de_loguear(tmp_path, monkeypatch):
    _flags_rotacion(monkeypatch, max_bytes=200, max_parts=2)
    h = _handler_de_archivo(tmp_path)
    try:
        for i in range(60):
            h.emit(_record("y" * 100))
        h.emit(_record("ULTIMA-LINEA-VISIBLE"))
    finally:
        h.close()

    hoy = f"{date.today():%Y-%m-%d}"
    assert not (tmp_path / f"stacky-{hoy}.3.log").exists()
    ultima = tmp_path / f"stacky-{hoy}.2.log"
    assert ultima.exists()
    assert "ULTIMA-LINEA-VISIBLE" in ultima.read_text(encoding="utf-8")


def test_purga_corre_al_arrancar(tmp_path, handler_limpio):
    viejo = tmp_path / f"stacky-{date.today() - timedelta(days=30):%Y-%m-%d}.log"
    viejo.write_text("viejo\n", encoding="utf-8")

    lfl.install_file_log_handler(base_dir=tmp_path)
    assert not viejo.exists(), "la purga no corrio al instalar el handler"

    otro = tmp_path / f"stacky-{date.today() - timedelta(days=40):%Y-%m-%d}.log"
    otro.write_text("otro\n", encoding="utf-8")
    assert lfl.purge_old_logs(tmp_path, 14) == 1


def test_purga_respeta_retention_days_de_config(tmp_path, monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_LOG_RETENTION_DAYS", 2, raising=False)
    reciente = tmp_path / f"stacky-{date.today() - timedelta(days=1):%Y-%m-%d}.log"
    viejo = tmp_path / f"stacky-{date.today() - timedelta(days=5):%Y-%m-%d}.log"
    reciente.write_text("r\n", encoding="utf-8")
    viejo.write_text("v\n", encoding="utf-8")

    assert lfl.purge_old_logs(tmp_path) == 1
    assert reciente.exists()
    assert not viejo.exists()


def test_purga_matchea_partes_numeradas(tmp_path):
    """C13 — el glob ya las ve; el bug real estaba en `_date_from_log_name`."""
    parte = tmp_path / f"stacky-{date.today() - timedelta(days=30):%Y-%m-%d}.3.log"
    parte.write_text("parte vieja\n", encoding="utf-8")

    assert lfl.purge_old_logs(tmp_path, 14) == 1
    assert not parte.exists()


def test_purga_ignora_archivo_tomado_y_sigue(tmp_path, monkeypatch):
    tomado = tmp_path / f"stacky-{date.today() - timedelta(days=30):%Y-%m-%d}.log"
    libre = tmp_path / f"stacky-{date.today() - timedelta(days=31):%Y-%m-%d}.log"
    tomado.write_text("t\n", encoding="utf-8")
    libre.write_text("l\n", encoding="utf-8")

    real_unlink = Path.unlink

    def _unlink(self, *a, **kw):
        if self.name == tomado.name:
            raise PermissionError("archivo tomado por otro proceso")
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", _unlink)

    assert lfl.purge_old_logs(tmp_path, 14) == 1
    assert tomado.exists()


def test_recent_log_files_incluye_partes_numeradas(tmp_path):
    """Guardia anti-regresion del ZIP de /api/diag/logs/export."""
    hoy = f"{date.today():%Y-%m-%d}"
    base = tmp_path / f"stacky-{hoy}.log"
    parte = tmp_path / f"stacky-{hoy}.2.log"
    base.write_text("b\n", encoding="utf-8")
    parte.write_text("p\n", encoding="utf-8")

    nombres = {p.name for p in lfl.recent_log_files(days=3, base_dir=tmp_path)}
    assert nombres == {base.name, parte.name}


def test_date_from_log_name_parsea_partes():
    esperado = date(2026, 6, 1)
    assert lfl._date_from_log_name(Path("stacky-2026-06-01.log")) == esperado
    assert lfl._date_from_log_name(Path("stacky-2026-06-01.3.log")) == esperado
    assert lfl._date_from_log_name(Path("stacky-basura.log")) is None
    assert lfl._date_from_log_name(Path("otra-cosa.log")) is None
