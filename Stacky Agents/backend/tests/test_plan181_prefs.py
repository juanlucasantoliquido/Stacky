"""Plan 181 F2 — MaskingPrefs v1: store en disco (atómico, sin cache, clave canónica).

Ver Stacky Agents/docs/181_PLAN_MASKING_DETERMINISTA_DE_SECRETOS_EN_EL_DATA_DIFF_*.md #F2.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest

from services import dbcompare_masking as m


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "data_dir", lambda: tmp_path)
    return tmp_path


def test_prefs_vacias_por_default():
    prefs = m.load_prefs()
    assert prefs == {"version": 1, "overrides": {}}


def test_set_visible_y_masked_persisten(_isolated_data_dir):
    # args en case mixto -> clave guardada en UPPERCASE (fix C3).
    m.set_override("dbo", "RUSUARIOS", "Password", "visible")
    m.set_override("dbo", "RPARAM", "Valor", "masked")
    prefs = m.load_prefs()
    assert "DBO.RUSUARIOS.PASSWORD" in prefs["overrides"]
    assert "DBO.RPARAM.VALOR" in prefs["overrides"]
    assert prefs["overrides"]["DBO.RUSUARIOS.PASSWORD"]["state"] == "visible"
    assert prefs["overrides"]["DBO.RPARAM.VALOR"]["state"] == "masked"
    # persistido en disco
    raw = json.loads((_isolated_data_dir / "db_compare" / "masking_prefs.json").read_text(encoding="utf-8"))
    assert raw["overrides"]["DBO.RUSUARIOS.PASSWORD"]["state"] == "visible"


def test_auto_elimina_override():
    m.set_override("dbo", "RUSUARIOS", "Password", "visible")
    assert "DBO.RUSUARIOS.PASSWORD" in m.load_prefs()["overrides"]
    # eliminar con case distinto: la clave canónica hace que igual matchee.
    m.set_override("DBO", "rusuarios", "PASSWORD", "auto")
    assert "DBO.RUSUARIOS.PASSWORD" not in m.load_prefs()["overrides"]


def test_override_visible_persiste_y_releen_disco(_isolated_data_dir):
    # KPI-3: el override sobrevive un "reinicio" (releer disco) sin cache.
    m.set_override("dbo", "RUSUARIOS", "Password", "visible")
    # Simular reinicio: el módulo no tiene estado; load_prefs relee de disco.
    prefs = m.load_prefs()
    assert prefs["overrides"]["DBO.RUSUARIOS.PASSWORD"]["state"] == "visible"
    # Cada load_prefs devuelve un objeto NUEVO (cero estado en memoria).
    assert m.load_prefs() is not m.load_prefs()


def test_state_invalido_lanza():
    with pytest.raises(ValueError):
        m.set_override("dbo", "T", "C", "nope")


def test_archivo_corrupto_degrada_vacio(_isolated_data_dir):
    d = _isolated_data_dir / "db_compare"
    d.mkdir(parents=True, exist_ok=True)
    (d / "masking_prefs.json").write_text("{ no es json ", encoding="utf-8")
    assert m.load_prefs() == {"version": 1, "overrides": {}}


def test_escritura_atomica_sin_tmp(_isolated_data_dir):
    m.set_override("dbo", "T", "C", "masked")
    d = _isolated_data_dir / "db_compare"
    # tras os.replace no queda el .tmp
    assert not (d / "masking_prefs.json.tmp").exists()
    assert (d / "masking_prefs.json").exists()
