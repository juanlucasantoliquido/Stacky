"""tests/test_plan89_environment_plan_apply.py — F2: plan_environment /
apply_environment (plan-then-apply NO destructivo) + centinela anti-destrucción.
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from services.environment_init import (
    apply_environment,
    plan_environment,
    validate_root,
)


def test_f2_validate_root_rules(tmp_path):
    assert validate_root("") is not None
    assert validate_root("relativo/x") is not None
    disk_root = os.path.splitdrive(str(tmp_path))[0] + os.sep if os.name == "nt" else "/"
    assert validate_root(disk_root) is not None
    assert validate_root(str(tmp_path)) is None


def test_f2_plan_fresh_all_to_create(tmp_path):
    result = plan_environment(str(tmp_path), ["IN_", "productivas", "salida"])
    assert result["root_exists"] is True
    assert isinstance(result["layout_fingerprint"], str) and result["layout_fingerprint"]
    assert result["summary"]["to_create"] == 3
    assert all(e["status"] == "to_create" for e in result["entries"])


def test_f2_plan_existing_dir_exists_ok(tmp_path):
    (tmp_path / "IN_").mkdir()
    result = plan_environment(str(tmp_path), ["IN_"])
    assert result["entries"][0]["status"] == "exists_ok"


def test_f2_plan_file_conflict(tmp_path):
    (tmp_path / "salida").write_text("archivo", encoding="utf-8")
    result = plan_environment(str(tmp_path), ["salida"])
    assert result["entries"][0]["status"] == "conflict"


def test_f2_plan_unsafe_traversal(tmp_path):
    result = plan_environment(str(tmp_path), ["../fuera"])
    entry = result["entries"][0]
    assert entry["status"] == "unsafe"
    assert entry["reason"] == "fuera_de_root"
    assert result["summary"]["to_create"] == 0


def test_f2_plan_symlink_escape_unsafe(tmp_path):
    ext = tmp_path.parent / f"ext_{tmp_path.name}"
    ext.mkdir(exist_ok=True)
    link = tmp_path / "link"
    try:
        os.symlink(str(ext), str(link), target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink no soportado en este entorno")
    result = plan_environment(str(tmp_path), ["link/sub"])
    entry = result["entries"][0]
    assert entry["status"] == "unsafe"
    assert entry["reason"] == "fuera_de_root"


def test_f2_plan_long_path_unsafe(tmp_path):
    long_rel = "a" * 300
    result = plan_environment(str(tmp_path), [long_rel])
    entry = result["entries"][0]
    assert entry["status"] == "unsafe"
    assert entry["reason"] == "path_demasiado_largo"


def test_f2_plan_fingerprint_stable_and_sensitive(tmp_path):
    r1 = plan_environment(str(tmp_path), ["IN_", "salida"])
    r2 = plan_environment(str(tmp_path), ["IN_", "salida"])
    assert r1["layout_fingerprint"] == r2["layout_fingerprint"]
    r3 = plan_environment(str(tmp_path), ["IN_", "salida", "extra"])
    assert r3["layout_fingerprint"] != r1["layout_fingerprint"]


def test_f2_apply_creates_only_to_create(tmp_path):
    (tmp_path / "salida").write_text("contenido-original", encoding="utf-8")
    before = (tmp_path / "salida").read_bytes()
    result = apply_environment(str(tmp_path), ["IN_", "productivas", "salida"])
    assert set(result["created"]) == {"IN_", "productivas"}
    assert result["conflicts"] == ["salida"]
    after = (tmp_path / "salida").read_bytes()
    assert before == after
    assert (tmp_path / "IN_").is_dir()
    assert (tmp_path / "productivas").is_dir()


def test_f2_apply_idempotent_second_run_zero(tmp_path):
    apply_environment(str(tmp_path), ["IN_", "productivas"])
    second = apply_environment(str(tmp_path), ["IN_", "productivas"])
    assert second["created"] == []
    plan_after = plan_environment(str(tmp_path), ["IN_", "productivas"])
    assert all(e["status"] == "exists_ok" for e in plan_after["entries"])


def test_f2_apply_unsafe_never_created(tmp_path):
    before_parent = set(os.listdir(tmp_path.parent))
    apply_environment(str(tmp_path), ["../fuera"])
    after_parent = set(os.listdir(tmp_path.parent))
    assert before_parent == after_parent


def test_f2_apply_partial_failure_reported(tmp_path):
    real_makedirs = os.makedirs

    def flaky_makedirs(path, exist_ok=False):
        if "b" in os.path.basename(path):
            raise OSError("denegado")
        return real_makedirs(path, exist_ok=exist_ok)

    with patch("services.environment_init.os.makedirs", side_effect=flaky_makedirs):
        result = apply_environment(str(tmp_path), ["a", "b", "c"])
    assert set(result["created"]) == {"a", "c"}
    assert len(result["failed"]) == 1
    assert result["failed"][0]["path"] == "b"
    assert "denegado" in result["failed"][0]["error"]


def test_f2_source_has_no_destructive_calls():
    src = (Path(__file__).parent.parent / "services" / "environment_init.py").read_text(encoding="utf-8")
    forbidden = [
        "rmtree", "rmdir", "unlink", "os.remove", "os.replace", "rename",
        "shutil.move", "open(",
    ]
    for token in forbidden:
        assert token not in src, f"Llamada destructiva prohibida encontrada: {token}"
