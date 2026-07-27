"""tests/test_plan255_silence_ratchet.py — Plan 255 F3.

RATCHET del silencio: `mudos_totales` (handlers catch-all cuyo cuerpo es solo
`pass` O solo `note_swallowed(...)`) solo puede BAJAR, POR ARCHIVO.

Este test SOLO COMPARA. El baseline se genera y se commitea con un comando
SEPARADO — `python -m services.silence_audit --write-baseline` — porque un
baseline autogenerado por el test que valida contra el baseline pasa siempre por
construcción y no valida nada.

Espejo de tests/test_plan218_coupling_ratchet.py.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.silence_audit import (  # noqa: E402
    classify_source,
    compare_to_baseline,
    paquete_de,
    scan_silent_handlers,
)

_BASELINE_PATH = _BACKEND / "tests" / "silence_ratchet_baseline.json"
_REGEN = "python -m services.silence_audit --write-baseline"


def _baseline() -> dict:
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


# ── El escáner ────────────────────────────────────────────────────────────────


def test_scan_es_determinista():
    assert scan_silent_handlers() == scan_silent_handlers()


def test_scan_excluye_tests_y_venv():
    scan = scan_silent_handlers()
    for clave in ("mudos_totales", "mudos_sin_contador", "silence_ok"):
        for ruta in scan[clave]:
            assert not ruta.startswith("tests/"), ruta
            assert ".venv/" not in ruta and not ruta.startswith("venv/"), ruta
            assert "__pycache__" not in ruta, ruta
            assert "node_modules" not in ruta, ruta


def test_ratchet_no_se_escanea_a_si_mismo():
    """La prosa de un artefacto chocando con su propio gate es un gotcha de la casa."""
    scan = scan_silent_handlers()
    for clave in ("mudos_totales", "mudos_sin_contador", "silence_ok"):
        assert "services/silence_audit.py" not in scan[clave]


def test_ratchet_detecta_pass_en_una_linea():
    """El AST ve igual la forma de una línea que la multilínea; el grep de v1 no."""
    una_linea = "try:\n    f()\nexcept Exception: pass\n"
    multilinea = "try:\n    f()\nexcept Exception:\n    # comentario\n    pass\n"
    assert classify_source(una_linea)["mudos_totales"] == 1
    assert classify_source(multilinea)["mudos_totales"] == 1
    assert classify_source(multilinea)["mudos_sin_contador"] == 1


def test_ratchet_respeta_silence_ok():
    src = (
        "try:\n"
        "    f()\n"
        "except Exception:\n"
        "    # silence-ok: el proceso ya estaba muerto\n"
        "    pass\n"
    )
    r = classify_source(src)
    assert r["mudos_totales"] == 0
    assert r["silence_ok"] == 1


def test_ratchet_silence_ok_sin_motivo_no_exime():
    """Obligar a ESCRIBIR el motivo es el punto entero del escape hatch."""
    src = "try:\n    f()\nexcept Exception:\n    # silence-ok:\n    pass\n"
    r = classify_source(src)
    assert r["mudos_totales"] == 1
    assert r["silence_ok"] == 0


def test_ratchet_note_swallowed_cuenta_como_mudo_total():
    """ANTI-GAMING (C2): instrumentar mueve el sitio de bucket, no lo saca del total."""
    crudo = "try:\n    f()\nexcept Exception:\n    pass\n"
    instrumentado = (
        "try:\n    f()\nexcept Exception as _e:\n    note_swallowed('mod.fn', _e)\n"
    )
    calificado = (
        "try:\n    f()\nexcept Exception as _e:\n    sfc.note_swallowed('mod.fn', _e)\n"
    )

    assert classify_source(crudo) == {"mudos_totales": 1, "mudos_sin_contador": 1,
                                      "silence_ok": 0}
    assert classify_source(instrumentado) == {"mudos_totales": 1,
                                              "mudos_sin_contador": 0, "silence_ok": 0}
    assert classify_source(calificado)["mudos_totales"] == 1


def test_scan_solo_cuenta_handlers_catch_all():
    """Un `except OSError: pass` es una decisión acotada, no un agujero."""
    assert classify_source("try:\n    f()\nexcept OSError:\n    pass\n")["mudos_totales"] == 0
    assert classify_source("try:\n    f()\nexcept (ValueError, Exception):\n    pass\n")["mudos_totales"] == 1


# ── La comparación contra el baseline ─────────────────────────────────────────


def test_ratchet_archivo_nuevo_arranca_en_cero():
    """Un archivo nuevo no puede nacer con deuda muda: su límite implícito es 0."""
    base = {"mudos_totales": {"services/viejo.py": 3}}
    scan = {"mudos_totales": {"services/viejo.py": 3, "services/nuevo.py": 1}}
    res = compare_to_baseline(scan, base)
    assert res["renames_posibles"] == []
    assert len(res["violations"]) == 1
    assert "services/nuevo.py" in res["violations"][0]


def test_ratchet_permite_bajar_sin_regenerar():
    """La comparación es `actual <= baseline`, no `==`."""
    base = {"mudos_totales": {"services/a.py": 5, "api/b.py": 2}}
    scan = {"mudos_totales": {"services/a.py": 1}}
    res = compare_to_baseline(scan, base)
    assert res["violations"] == []


def test_ratchet_rename_no_pone_rojo():
    """Un rename inocente no se convierte en deuda ajena (C16)."""
    base = {"mudos_totales": {"services/viejo.py": 4, "api/x.py": 1}}
    scan = {"mudos_totales": {"services/nuevo.py": 4, "api/x.py": 1}}
    res = compare_to_baseline(scan, base)
    assert res["violations"] == []
    assert len(res["renames_posibles"]) == 1
    assert "posible rename detectado" in res["renames_posibles"][0]
    assert "--write-baseline" in res["renames_posibles"][0]


def test_ratchet_rename_no_tapa_deuda_nueva():
    """Si el paquete CRECE, el rename deja de ser excusa."""
    base = {"mudos_totales": {"services/viejo.py": 4}}
    scan = {"mudos_totales": {"services/nuevo.py": 4, "services/otro.py": 3}}
    res = compare_to_baseline(scan, base)
    assert res["violations"], "el paquete creció de 4 a 7: eso es deuda nueva"


def test_paquete_de_reconoce_la_raiz():
    assert paquete_de("services/x.py") == "services"
    assert paquete_de("app.py") == "<raíz>"


def test_baseline_actual_es_verde():
    """El estado de HOY pasa.

    Si esto falla, se corre el comando de regeneración y se revisa el diff a
    mano; NUNCA se ajusta el número para que verdee.
    """
    res = compare_to_baseline(scan_silent_handlers(), _baseline())
    assert res["violations"] == [], (
        "RATCHET DE SILENCIO ROTO:\n" + "\n".join(res["violations"]) +
        f"\n\nRegeneración (solo si el cambio es legítimo): {_REGEN}"
    )


def test_el_test_nunca_escribe_el_baseline():
    """DoD: el baseline se commitea; este archivo jamás lo genera."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.Call):
            fn = nodo.func
            nombre = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            assert nombre != "write_baseline", "el meta-test no puede generar su baseline"
        if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").endswith("silence_audit"):
            assert "write_baseline" not in {a.name for a in nodo.names}
