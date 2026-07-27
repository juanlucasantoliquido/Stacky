"""Plan 255 F6 — canario de features dormidas.

Lo inverso a una huella de regresion: alarma cuando un patron BUENO deja de
aparecer. El test que cierra el circulo es
`test_resume_canary_habria_detectado_el_bug_de_e1`: prueba que este mecanismo
habria atrapado el bug que motivo el plan entero.

No toca la base: lee archivos de log sinteticos en un tmp_path.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

AHORA = datetime(2026, 7, 27, 12, 0, 0)


def _log(dir_: Path, fecha: datetime, lineas: list[str]) -> Path:
    p = dir_ / f"stacky-{fecha:%Y-%m-%d}.log"
    p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return p


def _dias(dir_: Path, n: int, lineas_por_dia=lambda d: []) -> list[Path]:
    """`n` archivos diarios, del mas nuevo al mas viejo."""
    paths = []
    for i in range(n):
        fecha = AHORA - timedelta(days=i)
        paths.append(_log(dir_, fecha, lineas_por_dia(i) or
                          [f"{fecha:%Y-%m-%d} 08:00:00 INFO [stacky] arranque"]))
    return paths


def _spec(**kw):
    from services.dormant_canary import CanarySpec

    base = dict(id="probe", label="Prueba", success_pattern=r"EXITO",
                gate_flags=(), max_silent_days=3, hint="mirá el historial")
    base.update(kw)
    return CanarySpec(**base)


@pytest.fixture()
def flags_on(monkeypatch):
    from config import config

    for k in ("CLAUDE_CODE_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_ENABLED",
              "STACKY_TELEMETRY_HARVEST_ENABLED",
              "STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED",
              "PROBE_FLAG"):
        monkeypatch.setattr(config, k, True, raising=False)
    yield


# ── Los 4 estados ─────────────────────────────────────────────────────────────


def test_canario_con_exito_reciente_es_ok(tmp_path, flags_on):
    from services.dormant_canary import check_canaries

    archivos = _dias(tmp_path, 4, lambda i: (
        [f"{AHORA:%Y-%m-%d} 09:31:02 INFO [x] EXITO del mecanismo"] if i == 0 else []
    ))
    fila = check_canaries(now=AHORA, canaries=[_spec()], log_files=archivos)[0]

    assert fila["status"] == "ok"
    assert fila["days_silent"] == 0
    assert fila["last_success_at"] == "2026-07-27T09:31:02"


def test_canario_sin_exito_y_flag_on_es_dormido(tmp_path, flags_on):
    from services.dormant_canary import check_canaries

    archivos = _dias(tmp_path, 4)  # cobertura suficiente, cero exitos
    fila = check_canaries(now=AHORA,
                          canaries=[_spec(gate_flags=("PROBE_FLAG",))],
                          log_files=archivos)[0]

    assert fila["status"] == "dormido"
    assert fila["gated_off"] is False
    assert fila["last_success_at"] is None
    assert fila["hint"]


def test_canario_con_flag_off_es_apagado_no_dormido(tmp_path, monkeypatch):
    """La regla que evita que el canario se vuelva RUIDO: el operador lo apago."""
    from config import config
    from services.dormant_canary import check_canaries

    monkeypatch.setattr(config, "PROBE_FLAG", False, raising=False)
    archivos = _dias(tmp_path, 4)
    fila = check_canaries(now=AHORA,
                          canaries=[_spec(gate_flags=("PROBE_FLAG",))],
                          log_files=archivos)[0]

    assert fila["status"] == "apagado"
    assert fila["gated_off"] is True


def test_canario_sin_log_suficiente_es_sin_datos(tmp_path, flags_on):
    """Nunca se afirma que algo esta muerto sin evidencia."""
    from services.dormant_canary import check_canaries

    archivos = _dias(tmp_path, 1)  # 1 dia para una ventana de 3
    fila = check_canaries(now=AHORA,
                          canaries=[_spec(gate_flags=("PROBE_FLAG",))],
                          log_files=archivos)[0]

    assert fila["status"] == "sin_datos"
    assert fila["days_silent"] is None


def test_check_canaries_no_muta_nada(tmp_path, flags_on):
    """AVISA, NUNCA ARREGLA: ni un archivo escrito, ni una config cambiada."""
    from config import config
    from services.dormant_canary import check_canaries

    archivos = _dias(tmp_path, 4)
    antes_fs = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                      for p in tmp_path.iterdir())
    antes_cfg = {k: getattr(config, k, None) for k in
                 ("CLAUDE_CODE_CLI_RESUME_ENABLED", "CODEX_CLI_RESUME_ENABLED",
                  "STACKY_TELEMETRY_HARVEST_ENABLED",
                  "STACKY_TELEMETRY_HARVEST_AUTOSCAN_ENABLED")}

    check_canaries(now=AHORA, log_files=archivos)

    despues_fs = sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns)
                        for p in tmp_path.iterdir())
    despues_cfg = {k: getattr(config, k, None) for k in antes_cfg}

    assert despues_fs == antes_fs, "el canario escribio o toco un archivo"
    assert despues_cfg == antes_cfg, "el canario cambio la configuracion"


# ── El test que cierra el circulo ─────────────────────────────────────────────


def test_resume_canary_habria_detectado_el_bug_de_e1(tmp_path, flags_on):
    """50 lineas de 'arranque en frio' y CERO de exito: el canario dice `dormido`.

    Es la evidencia literal de E1 (2026-07-17 a 2026-07-26). Prueba que este
    mecanismo habria atrapado el bug que motivo el plan entero, 9 dias antes.
    """
    from services.dormant_canary import check_canaries

    def _lineas(i):
        fecha = AHORA - timedelta(days=i)
        return [
            f"{fecha:%Y-%m-%d} 14:14:19 WARNING [harness.resume] harness.resume.resolve "
            f"falló (arranque en frío): Query.filter() being called on a Query which "
            f"already has LIMIT or OFFSET applied."
        ] * 13

    archivos = _dias(tmp_path, 4, _lineas)
    total = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in archivos)
    assert total >= 50, "la evidencia de E1 son 50 ocurrencias"

    filas = {f["id"]: f for f in check_canaries(now=AHORA, log_files=archivos)}
    assert filas["resume_efectivo"]["status"] == "dormido"
    assert filas["resume_efectivo"]["gated_off"] is False
    assert filas["resume_efectivo"]["last_success_at"] is None


def test_resume_canary_reconoce_las_tres_formas_del_exito(tmp_path, flags_on):
    """El camino de exito se loguea distinto en `resume.py` y en cada call-site."""
    from services.dormant_canary import check_canaries

    formas = [
        f"{AHORA:%Y-%m-%d} 09:00:01 INFO [harness.resume] resume claude_code_cli: "
        f"sesión=abc123def456… contexto cambió 12%",
        f"{AHORA:%Y-%m-%d} 09:00:02 INFO [codex] codex resume: "
        f"sesión previa=abc123def456… (H7.1)",
        f"{AHORA:%Y-%m-%d} 09:00:03 INFO [claude] re-run con --resume de "
        f"sesión previa (F2.3/H7.1): session_id=abc123def456…",
    ]
    for forma in formas:
        d = tmp_path / f"caso{formas.index(forma)}"
        d.mkdir()
        archivos = _dias(d, 4, lambda i, f=forma: [f] if i == 0 else [])
        filas = {r["id"]: r for r in check_canaries(now=AHORA, log_files=archivos)}
        assert filas["resume_efectivo"]["status"] == "ok", forma


def test_endpoint_diag_dormant_canaries():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/diag/dormant-canaries")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    ids = {c["id"] for c in data["canaries"]}
    assert ids == {"resume_efectivo", "telemetry_harvest", "ado_edit_learning_sweep"}
    for fila in data["canaries"]:
        assert fila["status"] in ("ok", "dormido", "apagado", "sin_datos")
        assert fila["hint"]
