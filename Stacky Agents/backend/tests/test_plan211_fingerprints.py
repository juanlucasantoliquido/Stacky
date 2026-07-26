"""Plan 211 F6 — Huellas de los dos patrones que este plan detecta.

Sirven para que el triage y el ciclo de auto-mejora sepan NOMBRAR "residuo de
port" y "efecto colateral de build peligroso".
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_PATH = REPO / "docs" / "sistema" / "error_fingerprints.json"
_IDS = ("port_residue_foreign_token", "build_side_effect_foreign")


def _data():
    if not _PATH.exists():
        pytest.skip("error_fingerprints.json no existe en este árbol")
    return json.loads(_PATH.read_text(encoding="utf-8"))


def test_fingerprints_valid_json():
    data = _data()

    assert isinstance(data.get("fingerprints"), list)


def test_two_fingerprints_present():
    entradas = {f.get("id"): f for f in _data()["fingerprints"]}

    for fid in _IDS:
        assert fid in entradas, f"falta la huella {fid}"
        assert entradas[fid]["guard_test"], f"{fid} sin test guardián"
        assert entradas[fid]["status"] == "resolved"


def test_guard_tests_existen():
    entradas = {f.get("id"): f for f in _data()["fingerprints"]}

    for fid in _IDS:
        ruta = entradas[fid]["guard_test"].split("::")[0]
        assert (ROOT / ruta).exists(), f"{fid} apunta a un test inexistente: {ruta}"


def test_sin_ids_duplicados():
    ids = [f.get("id") for f in _data()["fingerprints"]]

    assert len(ids) == len(set(ids))


def test_profile_default_trae_allowlist_vacia():
    path = ROOT / "services" / "client_profile_defaults" / "azure_devops.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["port_residue"]["allowlist"] == [], \
        "la allowlist nace vacía: cero trabajo del operador hasta que la necesite"
