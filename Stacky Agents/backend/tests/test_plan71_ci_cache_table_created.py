"""Plan 71 F2-bis — Tests: tabla ci_inference_cache se crea via create_all.

3 casos:
  1. Con el import de ci_inference_cache antes de create_all, la tabla existe.
  2. Sin el import (módulo no registrado), la tabla NO existe.
  3. Operación idempotente: create_all dos veces no falla.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase


class _Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# C1 — Tabla se crea cuando el modelo está importado antes de create_all
# ---------------------------------------------------------------------------
def test_table_created_when_module_imported():
    """Si importamos CIInferenceCache antes de create_all(), la tabla aparece."""
    # Importamos el modelo para que se registre en su Base (models.Base)
    import services.ci_inference_cache  # noqa: F401

    from models import Base as ModelsBase

    engine = create_engine("sqlite:///:memory:")
    ModelsBase.metadata.create_all(engine)

    insp = inspect(engine)
    assert "ci_inference_cache" in insp.get_table_names(), (
        "F2-bis: la tabla ci_inference_cache no fue creada por create_all"
    )


# ---------------------------------------------------------------------------
# C2 — Sin el import, la tabla NO debe estar registrada en una Base limpia
# ---------------------------------------------------------------------------
def test_table_not_present_in_clean_base():
    """Una Base limpia sin importar ci_inference_cache no crea la tabla."""
    engine = create_engine("sqlite:///:memory:")
    _Base.metadata.create_all(engine)
    insp = inspect(engine)
    assert "ci_inference_cache" not in insp.get_table_names()


# ---------------------------------------------------------------------------
# C3 — create_all es idempotente
# ---------------------------------------------------------------------------
def test_create_all_idempotent():
    """Llamar create_all dos veces sobre la misma DB no falla."""
    import services.ci_inference_cache  # noqa: F401
    from models import Base as ModelsBase

    engine = create_engine("sqlite:///:memory:")
    ModelsBase.metadata.create_all(engine)
    ModelsBase.metadata.create_all(engine)  # segunda vez: no debe lanzar
    insp = inspect(engine)
    assert "ci_inference_cache" in insp.get_table_names()
