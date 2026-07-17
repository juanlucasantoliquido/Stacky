"""tests/test_plan131_incident_store.py — Plan 131 F1.

Store de persistencia del intake (texto + archivos) previo al análisis.
Todos los tests monkeypatchean runtime_paths.data_dir → tmp_path (CERO
escritura fuera del sandbox de pytest).
"""
import pytest

import runtime_paths
from services import incident_store


@pytest.fixture(autouse=True)
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield tmp_path


def test_sanitize_filename_path_traversal():
    assert incident_store.sanitize_filename("..\\..\\x.png") == "x.png"
    assert incident_store.sanitize_filename("../../y.png") == "y.png"


def test_sanitize_filename_weird_chars():
    result = incident_store.sanitize_filename("pantalla:rota?.png")
    assert result == "pantalla_rota_.png"


def test_sanitize_filename_empty_falls_back():
    assert incident_store.sanitize_filename("") == "archivo"


def test_create_incident_happy_path():
    incident = incident_store.create_incident(
        "la pantalla se rompe",
        [("captura.png", b"\x89PNG-fake-bytes"), ("error.log", b"traceback aqui")],
    )
    assert incident["id"].startswith("inc_")
    assert incident["text"] == "la pantalla se rompe"
    assert len(incident["files"]) == 2
    names = {f["stored_name"] for f in incident["files"]}
    assert names == {"captura.png", "error.log"}
    for f in incident["files"]:
        assert f["sha256"]
        assert f["kind"] in ("image", "text")
    assert incident["status"] == "capturada"

    ledger = incident_store.list_incidents()
    assert len(ledger) == 1
    assert ledger[0]["id"] == incident["id"]


def test_create_incident_duplicate_names_real_collision():
    incident = incident_store.create_incident(
        "dup real",
        [("foo.png", b"111"), ("foo.png", b"222")],
    )
    names = sorted(f["stored_name"] for f in incident["files"])
    assert names == ["foo.png", "foo_2.png"]


def test_create_incident_ext_not_allowed():
    with pytest.raises(ValueError, match="ext_not_allowed"):
        incident_store.create_incident("texto", [("virus.exe", b"MZ")])


def test_create_incident_file_too_big():
    big = b"x" * (incident_store.MAX_FILE_BYTES + 1)
    with pytest.raises(ValueError, match="file_too_big"):
        incident_store.create_incident("texto", [("big.log", big)])


def test_create_incident_total_too_big():
    chunk = b"x" * (5 * 1024 * 1024)  # 5MB c/u
    files = [(f"f{i}.log", chunk) for i in range(6)]  # 30MB > 25MB total, 6 <= 10 files
    with pytest.raises(ValueError, match="total_too_big"):
        incident_store.create_incident("texto", files)


def test_create_incident_too_many_files():
    files = [(f"f{i}.log", b"x") for i in range(11)]
    with pytest.raises(ValueError, match="too_many_files"):
        incident_store.create_incident("texto", files)


def test_create_incident_empty_intake():
    with pytest.raises(ValueError, match="empty_intake"):
        incident_store.create_incident("   ", [])


def test_update_and_get_incident():
    incident = incident_store.create_incident("texto", [])
    updated = incident_store.update_incident(incident["id"], status="analizando", execution_id=42)
    assert updated["status"] == "analizando"
    assert updated["execution_id"] == 42

    fetched = incident_store.get_incident(incident["id"])
    assert fetched["status"] == "analizando"
    assert fetched["execution_id"] == 42

    ledger = incident_store.list_incidents()
    assert ledger[0]["status"] == "analizando"


def test_get_incident_missing_returns_none():
    assert incident_store.get_incident("inc_does_not_exist") is None


def test_update_incident_missing_raises():
    with pytest.raises(ValueError, match="incident_not_found"):
        incident_store.update_incident("inc_does_not_exist", status="error")
