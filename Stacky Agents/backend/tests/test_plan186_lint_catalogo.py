"""tests/test_plan186_lint_catalogo.py — Plan 186 F2 (ADICIÓN ARQUITECTO 2).

Selftest del catálogo de reglas: cada regla registrada declara un repro mínimo
embebido que la dispara. Canario anti-drift para cuando el catálogo crezca.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.pipeline_lint import _RULES, lint_yaml, SEV_ERROR, SEV_WARNING, SEV_INFO  # noqa: E402

_VALID_SEV = {SEV_ERROR, SEV_WARNING, SEV_INFO}


def test_todo_codigo_unico():
    codes = [entry[0] for entry in _RULES]
    assert len(codes) == len(set(codes)), f"códigos duplicados en _RULES: {codes}"


def test_severidades_validas():
    for code, severity, *_ in _RULES:
        assert severity in _VALID_SEV, f"{code}: severidad inválida {severity!r}"


def test_toda_regla_tiene_repro():
    for code, _sev, _prov, _fn, repro in _RULES:
        assert repro is not None, f"{code}: falta repro embebido"
        assert isinstance(repro, tuple) and len(repro) == 2, f"{code}: repro mal formado"


def test_todo_repro_dispara_su_regla():
    # known_variables=[] (vault vacío, estado runtime válido) para que PL013 —que se
    # omite con None— también pueda dispararse desde su repro.
    for code, _sev, _prov, _fn, repro in _RULES:
        provider, yaml_min = repro
        rep = lint_yaml(yaml_min, provider, known_variables=[])
        got = [f.code for f in rep.findings]
        assert code in got, f"{code}: su repro {provider} no lo dispara (obtuvo {got})"


def test_mensajes_no_vacios():
    # todo repro produce findings con mensaje no vacío (calidad es-AR).
    for _code, _sev, _prov, _fn, repro in _RULES:
        provider, yaml_min = repro
        rep = lint_yaml(yaml_min, provider, known_variables=[])
        for f in rep.findings:
            assert f.message and f.message.strip(), f"finding {f.code} con mensaje vacío"
