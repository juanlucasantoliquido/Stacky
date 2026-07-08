"""Plan 107 F1 — validate_sandbox_override (guard puro, sin I/O salvo realpath).

Tabla dorada §4.1 del plan (fuente única de verdad, replicada en TS por
environmentModel.sandbox.test.ts F5): G1..G9. Rutas construidas con tmp_path
para ser absolutas reales en el runner."""
import os

import pytest

from services.environment_init import validate_sandbox_override


def test_override_invalid_root_rejected(tmp_path):
    prod = str(tmp_path / "prod")
    assert validate_sandbox_override("relativo/x", prod) is not None  # G8


def test_override_equal_to_production_rejected(tmp_path):
    prod = str(tmp_path / "prod")
    assert validate_sandbox_override(prod, prod) == "sandbox_igual_a_produccion"  # G1


def test_override_inside_production_rejected(tmp_path):
    prod = str(tmp_path / "prod")
    override = str(tmp_path / "prod" / "sub")
    assert validate_sandbox_override(override, prod) == "sandbox_dentro_de_produccion"  # G2


def test_production_inside_override_rejected(tmp_path):
    prod = str(tmp_path / "prod" / "sub")
    override = str(tmp_path / "prod")
    assert validate_sandbox_override(override, prod) == "produccion_dentro_de_sandbox"  # G3


def test_disjoint_sibling_ok(tmp_path):
    prod = str(tmp_path / "prod")
    override = str(tmp_path / "prod-test")
    assert validate_sandbox_override(override, prod) is None  # G4 — hermano, NO prefijo


@pytest.mark.skipif(os.name != "nt", reason="drives distintos solo aplica en Windows")
def test_different_drive_ok():
    assert validate_sandbox_override(r"D:\sandbox", r"C:\prod") is None  # G6


def test_no_production_configured_accepts_valid_override(tmp_path):
    override = str(tmp_path / "sandbox")
    assert validate_sandbox_override(override, "") is None  # G7


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive es semántica de FS Windows")
def test_case_insensitive_overlap_rejected_windows(tmp_path):
    prod = tmp_path / "prod"
    prod.mkdir()
    override = str(prod).upper() + os.sep + "sub"
    assert validate_sandbox_override(override, str(prod)) == "sandbox_dentro_de_produccion"  # G5


def test_trailing_separator_equal_rejected(tmp_path):
    prod = tmp_path / "prod"
    prod.mkdir()
    override = str(prod) + os.sep
    assert validate_sandbox_override(override, str(prod)) == "sandbox_igual_a_produccion"  # G9
