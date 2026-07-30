"""Plan 262 F0.3 — el doc que miente sobre el default de la flag del 240.

DOS mentiras, no una (v2/C10):
  1. agenda_web_launcher.py:12 dice "default OFF por EXCEPCION DURA #3".
  2. config.py:1230-1231 repite la misma mentira JUSTO ENCIMA de un os.getenv(..., "true").

El caso 3 NO es un gate (pasa antes y despues): es una guarda de no-regresion.
"""
from __future__ import annotations

import re
from pathlib import Path

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _TOOL_ROOT.parent.parent
_LAUNCHER = _TOOL_ROOT / "agenda_web_launcher.py"
_CONFIG_PY = _REPO_ROOT / "Stacky Agents" / "backend" / "config.py"

_FLAG = "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"


def test_launcher_docstring_no_dice_default_off():
    """El docstring de modulo del launcher no puede afirmar 'default OFF'."""
    lines = _LAUNCHER.read_text(encoding="utf-8").splitlines()[:40]
    offenders = [
        f"{i}: {ln.strip()}"
        for i, ln in enumerate(lines, start=1)
        if "default off" in ln.lower()
    ]
    assert offenders == [], (
        "el docstring del launcher todavia dice 'default OFF' mientras config.py "
        f"declara 'true'. Lineas ofensoras: {offenders}"
    )


def test_config_no_dice_default_off_para_la_flag_del_240():
    """Las 5 lineas encima de la declaracion no pueden decir 'Default OFF'."""
    lines = _CONFIG_PY.read_text(encoding="utf-8").splitlines()
    idx = next(
        (i for i, ln in enumerate(lines) if _FLAG in ln and "os.getenv" not in ln),
        None,
    )
    assert idx is not None, f"no se encontro la declaracion de {_FLAG} en config.py"
    window = lines[max(0, idx - 5):idx]
    offenders = [
        f"{idx - len(window) + j + 1}: {ln.strip()}"
        for j, ln in enumerate(window)
        if "default off" in ln.lower()
    ]
    assert offenders == [], (
        "el comentario de config.py sigue diciendo 'Default OFF' encima de un "
        f"os.getenv(..., 'true'). Lineas ofensoras: {offenders}"
    )


def test_launcher_flag_default_es_on_en_config():
    """GUARDA DE NO-REGRESION (no es un gate: pasa antes y despues).

    Regex MULTILINEA a proposito: la declaracion ocupa 3 lineas y la key aparece
    en dos de ellas, asi que un regex por linea no matchea nunca (v2/C10).
    NO importa `config`: eso arrastraria el backend entero al proceso del tool.
    """
    text = _CONFIG_PY.read_text(encoding="utf-8")
    m = re.search(
        rf'{_FLAG}"?\s*:?\s*bool\s*=\s*os\.getenv\(\s*"{_FLAG}"\s*,\s*"(?P<def>[a-z]+)"',
        text,
        re.S,
    )
    assert m is not None, f"no se pudo parsear la declaracion de {_FLAG} en config.py"
    assert m.group("def") == "true", (
        f"el default efectivo de {_FLAG} es '{m.group('def')}', se esperaba 'true'"
    )
