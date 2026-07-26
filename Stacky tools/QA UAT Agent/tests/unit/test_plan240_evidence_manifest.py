"""test_plan240_evidence_manifest.py — Plan 240 F7 (cerrado por el Plan 241 F8).

Cada ejecucion deja un manifiesto de toda su evidencia con hash, re-verificable
despues con un comando.
"""
import pytest

from evidence_manifest import build_evidence_manifest, verify_evidence_manifest


def _seed(tmp_path):
    (tmp_path / "a.png").write_bytes(b"\x89PNG-fake")
    (tmp_path / "b.webm").write_bytes(b"webm-fake")
    (tmp_path / "c.json").write_text('{"ok": true}', encoding="utf-8")
    (tmp_path / "d.bin").write_bytes(b"raw")
    return tmp_path


def test_manifest_lista_y_clasifica(tmp_path):
    m = build_evidence_manifest(_seed(tmp_path))
    assert m["ok"] is True
    assert m["counts"]["screenshot"] == 1
    assert m["counts"]["video"] == 1
    assert m["counts"]["data"] == 1
    kinds = {f["path"]: f["kind"] for f in m["files"]}
    assert kinds["d.bin"] == "other"


def test_manifest_determinista(tmp_path):
    _seed(tmp_path)
    a = build_evidence_manifest(tmp_path)
    b = build_evidence_manifest(tmp_path)
    assert [(f["path"], f["sha256"]) for f in a["files"]] == \
           [(f["path"], f["sha256"]) for f in b["files"]]


def test_manifest_excluye_a_si_mismo(tmp_path):
    _seed(tmp_path)
    build_evidence_manifest(tmp_path)
    m2 = build_evidence_manifest(tmp_path)
    assert all(f["path"] != "evidence_manifest.json" for f in m2["files"])


def test_verify_ok(tmp_path):
    _seed(tmp_path)
    build_evidence_manifest(tmp_path)
    v = verify_evidence_manifest(tmp_path)
    assert v["ok"] is True
    assert v["mismatches"] == []


def test_verify_detecta_modificacion(tmp_path):
    _seed(tmp_path)
    build_evidence_manifest(tmp_path)
    (tmp_path / "a.png").write_bytes(b"\x89PNG-OTRO")
    v = verify_evidence_manifest(tmp_path)
    assert v["ok"] is False
    assert v["mismatches"][0]["reason"] in ("hash_mismatch", "size_mismatch")


def test_verify_detecta_borrado(tmp_path):
    _seed(tmp_path)
    build_evidence_manifest(tmp_path)
    (tmp_path / "b.webm").unlink()
    v = verify_evidence_manifest(tmp_path)
    assert v["ok"] is False
    assert "b.webm" in v["missing"]


def test_dir_inexistente_no_lanza(tmp_path):
    m = build_evidence_manifest(tmp_path / "nope")
    assert m["ok"] is False
    assert m["error"] == "run_dir_missing"


def test_subdirectorios_con_paths_relativos_posix(tmp_path):
    sub = tmp_path / "sub" / "dir"
    sub.mkdir(parents=True)
    (sub / "x.png").write_bytes(b"x")
    m = build_evidence_manifest(tmp_path)
    assert any(f["path"] == "sub/dir/x.png" for f in m["files"])
    assert all("\\" not in f["path"] for f in m["files"])


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
