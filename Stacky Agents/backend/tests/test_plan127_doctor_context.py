"""Plan 127 F4 — Refactor extractivo build_doctor_context_blocks (api/devops_section_doctor.py).

Función pura (salvo el render YAML condicional, que ya era el comportamiento
actual movido verbatim). Compartida por el doctor cloud (Plan 104) y el
doctor local (Plan 127, F5).
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest


def test_none_para_seccion_desconocida():
    from api.devops_section_doctor import build_doctor_context_blocks

    assert build_doctor_context_blocks("no_existe", "p", {}) is None


def test_context_incluye_instruccion_y_payload():
    from api.devops_section_doctor import SECTION_DOCTORS, build_doctor_context_blocks

    payload = {"foo": "bar"}
    blocks = build_doctor_context_blocks("environments", "proj-x", payload)
    assert blocks is not None
    assert len(blocks) == 1
    content = blocks[0]["content"]
    assert SECTION_DOCTORS["environments"]["instruction"] in content
    assert '"foo": "bar"' in content


def test_pipeline_renderiza_yaml_con_generador_on(monkeypatch):
    import config as cfg
    from api.devops_section_doctor import build_doctor_context_blocks

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_GENERATOR_ENABLED", True, raising=False)
    minimal_spec = {
        "name": "mi-pipeline",
        "stages": [{
            "name": "build",
            "jobs": [{"name": "job1", "steps": [{"name": "compilar", "script": "echo hola"}]}],
        }],
    }
    payload = {"spec": minimal_spec}
    blocks = build_doctor_context_blocks("pipeline", "proj-x", payload)
    assert blocks is not None
    assert "yaml_ado" in payload
    assert "yaml_gitlab" in payload
    assert payload["yaml_ado"] is not None
    assert payload["yaml_gitlab"] is not None
