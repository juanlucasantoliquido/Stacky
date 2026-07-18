"""Plan 181 F1 — Núcleo puro de masking: detectores, mask_value, masking_plan,
apply_masking. Todo con dicts a mano, sin disco ni Flask.

Ver Stacky Agents/docs/181_PLAN_MASKING_DETERMINISTA_DE_SECRETOS_EN_EL_DATA_DIFF_*.md #F1.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import dbcompare_masking as m


# ---------------------------------------------------------------------------
# Detectores por NOMBRE (KPI-5)
# ---------------------------------------------------------------------------


def test_nombres_sensibles_golden():
    for col in ("PASSWORD", "Contrasena", "API_KEY", "CADENA_CONEXION", "ClaveSecreta"):
        assert m.column_name_is_sensitive(col) is True, col
    for col in ("CLAVE", "DESCRIPCION", "EMAIL", "VALOR"):
        assert m.column_name_is_sensitive(col) is False, col
    # Contraseña con eñe normalizada a 'contrasena' igual matchea 'contrase'.
    assert m.column_name_is_sensitive("CONTRASENA") is True


def test_clave_a_secas_visible_compuestos_masked():
    assert m.column_name_is_sensitive("CLAVE") is False
    assert m.column_name_is_sensitive("CLAVE_SECRETA") is True
    assert m.column_name_is_sensitive("ClaveApi") is True
    assert m.column_name_is_sensitive("clave_privada") is True
    assert m.column_name_is_sensitive("clave_acceso") is True


# ---------------------------------------------------------------------------
# Detectores por VALOR (KPI-5) + mask_value (fix C4)
# ---------------------------------------------------------------------------


def test_valores_sensibles_golden():
    assert m.value_is_sensitive("eyJhbGciOiJIUzI1NiJ9.x") is True
    assert m.value_is_sensitive("Server=x;Password=y;") is True
    assert m.value_is_sensitive("hola") is False
    assert m.value_is_sensitive("12345678") is False
    assert m.value_is_sensitive(None) is False


def test_mask_value_regla_exacta():
    assert m.mask_value(None) is None
    assert m.mask_value("abc") == "••••"
    assert m.mask_value("secret") == "••••"  # 6 chars, SIN sufijo
    assert m.mask_value("supersecret42") == "••••42"  # 13 chars, con sufijo


# ---------------------------------------------------------------------------
# masking_plan — precedencia y muestreo
# ---------------------------------------------------------------------------


def _diff(columns, **over):
    base = {
        "schema": "dbo",
        "table": "RUSUARIOS",
        "columns": columns,
        "only_source": [],
        "only_target": [],
        "changed": [],
    }
    base.update(over)
    return base


def test_plan_precedencia_override_gana():
    td = _diff(["PASSWORD", "DESCRIPCION"])
    prefs = {
        "overrides": {
            "DBO.RUSUARIOS.PASSWORD": {"state": "visible"},
            "DBO.RUSUARIOS.DESCRIPCION": {"state": "masked"},
        }
    }
    plan = m.masking_plan(td, prefs)
    assert plan["PASSWORD"] == "visible"  # override gana sobre el detector de nombre
    assert plan["DESCRIPCION"] == "masked"  # override fuerza masked


def test_plan_override_visible_no_reenmascarado_por_valor():
    # Override visible sobre columna cuyo valor es un JWT: NO se re-enmascara.
    td = _diff(["VALOR"], only_source=[{"VALOR": "eyJhbGciOiJIUzI1NiJ9.zzzzz"}])
    prefs = {"overrides": {"DBO.RUSUARIOS.VALOR": {"state": "visible"}}}
    plan = m.masking_plan(td, prefs)
    assert plan["VALOR"] == "visible"


def test_override_case_cruzado():
    # Override guardado en clave canónica upper aplica aunque el diff traiga
    # el schema/table en distinto case (fix C3).
    td = {"schema": "DBO", "table": "RUSUARIOS", "columns": ["PASSWORD"],
          "only_source": [], "only_target": [], "changed": []}
    prefs = {"overrides": {"DBO.RUSUARIOS.PASSWORD": {"state": "visible"}}}
    plan = m.masking_plan(td, prefs)
    assert plan["PASSWORD"] == "visible"


def test_plan_valor_solo_si_nombre_no_decidio():
    # Columna VALOR (nombre neutro) con un JWT en la fila 1 -> masked.
    td = _diff(["VALOR"], only_source=[{"VALOR": "eyJhbGciOiJIUzI1NiJ9.abc"}])
    assert m.masking_plan(td, {})["VALOR"] == "masked"
    # El mismo JWT más allá de la fila 50 (muestreo determinista) -> visible.
    rows = [{"VALOR": "hola"} for _ in range(60)]
    rows[55]["VALOR"] = "eyJhbGciOiJIUzI1NiJ9.abc"
    td2 = _diff(["VALOR"], only_source=rows)
    assert m.masking_plan(td2, {})["VALOR"] == "visible"


# ---------------------------------------------------------------------------
# apply_masking — 4 apariciones (KPI-1), no muta (KPI-6), sin masked no copia
# ---------------------------------------------------------------------------


def _diff_full():
    return {
        "schema": "dbo",
        "table": "RUSUARIOS",
        "columns": ["ID", "PASSWORD"],
        "pk_cols": ["ID"],
        "only_source": [{"ID": "3", "PASSWORD": "supersecret42"}],
        "only_target": [{"ID": "4", "PASSWORD": "hunter2xyzzz"}],
        "changed": [{"pk": {"ID": "5"}, "cells": {"PASSWORD": {"source": "oldpass9988", "target": "newpass7766"}}}],
    }


def test_apply_cuatro_apariciones():
    td = _diff_full()
    plan = m.masking_plan(td, {})
    out = m.apply_masking(td, plan)
    assert out["only_source"][0]["PASSWORD"] == "••••42"
    assert out["only_target"][0]["PASSWORD"] == "••••zz"
    assert out["changed"][0]["cells"]["PASSWORD"]["source"] == "••••88"
    assert out["changed"][0]["cells"]["PASSWORD"]["target"] == "••••66"
    assert out["masked_columns"] == ["PASSWORD"]
    # La PK (ID) no es sensible: intacta.
    assert out["only_source"][0]["ID"] == "3"


def test_apply_pk_sensible_enmascarada():
    td = {
        "schema": "dbo", "table": "T", "columns": ["TOKEN"], "pk_cols": ["TOKEN"],
        "only_source": [], "only_target": [],
        "changed": [{"pk": {"TOKEN": "abcdefghij"}, "cells": {}}],
    }
    out = m.apply_masking(td, m.masking_plan(td, {}))
    assert out["changed"][0]["pk"]["TOKEN"] == "••••ij"
    assert out["masked_columns"] == ["TOKEN"]


def test_apply_no_muta_original():
    import copy
    td = _diff_full()
    snapshot = copy.deepcopy(td)
    m.apply_masking(td, m.masking_plan(td, {}))
    assert td == snapshot  # KPI-6: la entrada quedó estructuralmente idéntica


def test_apply_sin_masked_no_copia_profunda():
    td = {
        "schema": "dbo", "table": "T", "columns": ["ID", "DESCRIPCION"],
        "only_source": [{"ID": "1", "DESCRIPCION": "hola"}],
        "only_target": [], "changed": [],
    }
    out = m.apply_masking(td, m.masking_plan(td, {}))
    assert out["only_source"] is td["only_source"]  # misma referencia: cero costo
    assert out["masked_columns"] == []
