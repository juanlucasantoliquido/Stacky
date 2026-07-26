"""Plan 210 F6 — El prompt del Developer ya no siembra un build verde narrado.

OJO: los asserts grepean el ARCHIVO DEL PROMPT, nunca el doc del plan (que sí
menciona el claim en su prosa).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_PROMPT = ROOT / "Stacky" / "agents" / "Developer.agent.md"
_GREEN_CLAIM = re.compile(r"color:green[^>]*>\s*<strong>\s*.{0,3}Build OK", re.IGNORECASE)


def _texto() -> str:
    return _PROMPT.read_text(encoding="utf-8")


def test_no_hardcoded_build_ok_seed():
    texto = _texto()

    assert "requerida. Build OK." not in texto, \
        "el ejemplo del RESUMEN ya no puede sembrar un build verde narrado"


def test_build_section_is_machine_authored():
    texto = _texto()

    assert "verificado por máquina" in texto
    assert not _GREEN_CLAIM.search(texto), \
        "el span verde hardcodeado del prompt tiene que desaparecer"


def test_paso4_calls_verify_endpoint():
    texto = _texto()

    assert "dev/build-verify" in texto
    assert "VEREDICTO DE MÁQUINA" in texto
    assert "ausencia de veredicto = no verificado" in texto


def test_version_bumped():
    texto = _texto()

    assert 'version: "2.2.0"' in texto
    assert "v2.2.0 — Stacky Agents." in texto


def test_documenta_la_resolucion_de_entrada():
    texto = _texto()

    assert "allow_csproj_entry" in texto, \
        "el prompt debe decir que un .csproj suelto no cuenta salvo opt-in"
