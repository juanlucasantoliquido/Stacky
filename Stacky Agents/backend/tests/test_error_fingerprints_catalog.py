"""Plan 163 F4 — schema-test del catalogo de huellas error_fingerprints.json.

Valida: JSON valido, sin ids duplicados, patrones que compilan, self_test
coherente, CERO bytes de control crudos (C1), ruta canonica .json.
"""
import sys
import re
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from runtime_paths import backend_root

_CATALOG = backend_root().parent / "docs" / "sistema" / "error_fingerprints.json"

_STATUS_ENUM = {"resolved", "open", "by_design"}
_REQUIRED = ("id", "title", "class", "status", "log_pattern", "log_guarded", "killed_by", "guard_test", "self_test")


def _load() -> dict:
    return json.loads(_CATALOG.read_text(encoding="utf-8"))


def test_json_valido():
    assert _CATALOG.exists()
    data = _load()
    assert data["schema_version"] == 1
    assert isinstance(data["fingerprints"], list) and data["fingerprints"]


def test_campos_obligatorios():
    for fp in _load()["fingerprints"]:
        for key in _REQUIRED:
            assert key in fp, f"huella {fp.get('id')!r} sin campo {key!r}"


def test_sin_ids_duplicados():
    ids = [fp["id"] for fp in _load()["fingerprints"]]
    assert len(ids) == len(set(ids))


def test_status_enum():
    for fp in _load()["fingerprints"]:
        assert fp["status"] in _STATUS_ENUM


def test_patrones_compilan():
    for fp in _load()["fingerprints"]:
        re.compile(fp["log_pattern"])  # no debe lanzar


def test_self_test_coherente():
    for fp in _load()["fingerprints"]:
        pat = fp["log_pattern"]
        for sample in fp["self_test"]["matches"]:
            assert re.search(pat, sample), f"{fp['id']}: match esperado fallo en {sample!r}"
        for sample in fp["self_test"]["clean"]:
            assert not re.search(pat, sample), f"{fp['id']}: clean matcheo indebidamente {sample!r}"


def test_sin_control_chars_crudos():
    """C1: ningun byte de control crudo 0x00-0x1F fuera de \\n \\r \\t (ni ESC 0x1B)."""
    raw = _CATALOG.read_bytes()
    offending = [b for b in raw if b < 0x20 and b not in (0x09, 0x0A, 0x0D)]
    assert offending == [], f"bytes de control crudos en el catalogo: {sorted(set(offending))}"


def test_ruta_canonica():
    assert _CATALOG.suffix == ".json"
    assert _CATALOG.parent.name == "sistema"
    assert _CATALOG.parent.parent.name == "docs"
