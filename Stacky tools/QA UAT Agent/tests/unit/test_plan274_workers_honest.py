"""
test_plan274_workers_honest.py — Plan 274 F3.

Que `QA_UAT_WORKERS` signifique algo, y que subirlo NO PUEDA romper la sesion
WebForms por accidente.

ESTA FASE NO SUBE EL PARALELISMO. Sube la HONESTIDAD: el default efectivo sigue
siendo 1 worker. Hoy `playwright.config.ts:13` lee
`workers: Number(process.env.QA_UAT_WORKERS ?? 1)` y el runner inyecta
`"--workers=1"` hardcodeado en el CLI (`uat_test_runner.py:355`), que PISA el
config. Resultado: setear QA_UAT_WORKERS=4 no hace absolutamente nada.

POR QUE NO SE HABILITA: AgendaWeb es ASP.NET WebForms y el `storageState`
compartido (`playwright.config.ts:27`) lleva UNA sola cookie ASP.NET_SessionId.
Dos workers con la misma sesion de servidor se pisan el ViewState. Subir workers
sin sesion por worker ROMPE el subsistema (R-2).
"""
from __future__ import annotations

import logging
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
RUNNER = TOOL_ROOT / "uat_test_runner.py"


def _resolve(monkeypatch, **env) -> int:
    import uat_test_runner
    monkeypatch.delenv("QA_UAT_WORKERS", raising=False)
    monkeypatch.delenv("STACKY_QA_UAT_RESPECT_WORKERS_ENABLED", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return uat_test_runner._resolve_workers()


def test_default_sigue_siendo_un_worker(monkeypatch):
    """Sin env vars, el comportamiento observable no cambia."""
    assert _resolve(monkeypatch) == 1


def test_flag_off_devuelve_uno(monkeypatch):
    """Rollback exacto por flag: comportamiento historico, aunque pidan 4."""
    assert _resolve(monkeypatch,
                    STACKY_QA_UAT_RESPECT_WORKERS_ENABLED="false",
                    QA_UAT_WORKERS="4") == 1


def test_workers_altos_se_bloquean_por_sesion(monkeypatch, caplog):
    """R-2: la guardia de sesion fuerza 1 y DICE POR QUE."""
    with caplog.at_level(logging.WARNING, logger="stacky.qa_uat.test_runner"):
        n = _resolve(monkeypatch, QA_UAT_WORKERS="4")
    assert n == 1, f"con QA_UAT_WORKERS=4 y sesion compartida hay que forzar 1, dio {n}"
    assert any("sesion unica" in r.getMessage() for r in caplog.records), (
        "la guardia tiene que explicar el motivo (sesion unica en storageState), "
        f"no bajar el numero en silencio. Mensajes: {[r.getMessage() for r in caplog.records]}")


def test_basura_no_crashea(monkeypatch):
    """Un valor invalido nunca puede tumbar una corrida."""
    assert _resolve(monkeypatch, QA_UAT_WORKERS="abc") == 1
    assert _resolve(monkeypatch, QA_UAT_WORKERS="") == 1
    assert _resolve(monkeypatch, QA_UAT_WORKERS="-3") == 1


def test_el_comando_ya_no_hardcodea_uno():
    """CORRE CONTRA EL DEFECTO: con el codigo de hoy da ROJO."""
    src = RUNNER.read_text(encoding="utf-8")
    assert '"--workers=1"' not in src, (
        'uat_test_runner.py sigue inyectando el literal "--workers=1" en el '
        "comando CLI, que PISA el workers del playwright.config.ts. La config "
        "del operador seguiria siendo una mentira.")
    assert "_resolve_workers()" in src, (
        "no aparece _resolve_workers(): el numero de workers tiene que salir de "
        "una funcion con guardia de sesion, no de un literal")
