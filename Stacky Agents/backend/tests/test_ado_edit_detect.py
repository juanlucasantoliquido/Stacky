"""Plan 60 F2 — Tests del detector puro de ediciones humanas (harness/ado_edit_detect.py).

Los 9 casos del plan (incluyendo fixture-contrato de shape de ADO /updates) + borde.
"""
from __future__ import annotations


# Fixture-contrato: shape real de ADO /updates según la documentación de la API.
_SHAPE_REAL = {
    "rev": 2,
    "revisedBy": {"uniqueName": "op@x", "displayName": "Op"},
    "fields": {
        "System.Description": {
            "oldValue": "<p>a</p>",
            "newValue": "<p>a b extendido con cambio importante</p>",
        }
    },
}

_STACKY_REV_1 = {
    "rev": 1,
    "revisedBy": {"uniqueName": "stacky-svc@example.com", "displayName": "Stacky Service"},
    "fields": {
        "System.Description": {
            "oldValue": "",
            "newValue": "<h1>EP-1 Épica</h1><h2>RF-1</h2><p>Original.</p>",
        }
    },
}

_HUMAN_REV_2 = {
    "rev": 2,
    "revisedBy": {"uniqueName": "operador@empresa.com", "displayName": "Operador"},
    "fields": {
        "System.Description": {
            "oldValue": "<h1>EP-1 Épica</h1><h2>RF-1</h2><p>Original.</p>",
            "newValue": "<h1>EP-1 Épica</h1><h2>RF-1</h2><p>Original. Corregido por humano.</p>",
        }
    },
}


def test_only_stacky_revision_returns_none():
    """Solo revisión 1 (creación por Stacky) → None (sin edición humana)."""
    from harness.ado_edit_detect import is_human_edit
    result = is_human_edit(
        _STACKY_REV_1,
        baseline_rev=1,
        baseline_author="stacky-svc@example.com",
        service_identities=set(),
    )
    assert result is None


def test_human_revision_returns_human_edit():
    """Rev 2 con autor ≠ baseline_author y System.Description cambiado → HumanEdit(rev=2)."""
    from harness.ado_edit_detect import is_human_edit
    result = is_human_edit(
        _HUMAN_REV_2,
        baseline_rev=1,
        baseline_author="stacky-svc@example.com",
        service_identities=set(),
    )
    assert result is not None
    assert result.rev == 2


def test_service_identity_in_set_returns_none():
    """Autor en service_identities → None (no es edición humana)."""
    from harness.ado_edit_detect import is_human_edit
    result = is_human_edit(
        _HUMAN_REV_2,
        baseline_rev=1,
        baseline_author="stacky-svc@example.com",
        service_identities={"operador@empresa.com"},
    )
    assert result is None


def test_rev_not_touching_body_returns_none():
    """Rev que no toca System.Description → None."""
    from harness.ado_edit_detect import is_human_edit
    rev_no_body = {
        "rev": 2,
        "revisedBy": {"uniqueName": "operador@empresa.com"},
        "fields": {
            "System.State": {"oldValue": "New", "newValue": "Active"},
        },
    }
    result = is_human_edit(
        rev_no_body,
        baseline_rev=1,
        baseline_author="stacky-svc@example.com",
        service_identities=set(),
    )
    assert result is None


def test_already_processed_rev_returns_none():
    """Rev ya en already_processed_revs → None (idempotencia)."""
    from harness.ado_edit_detect import select_latest_human_edit
    result = select_latest_human_edit(
        [_HUMAN_REV_2],
        baseline_rev=1,
        baseline_author="stacky-svc@example.com",
        service_identities=set(),
        already_processed_revs={2},
    )
    assert result is None


def test_select_latest_returns_highest_rev():
    """Revisiones 2 y 3 humanas, ninguna procesada → devuelve rev=3 (la más reciente)."""
    from harness.ado_edit_detect import select_latest_human_edit
    rev3 = {
        "rev": 3,
        "revisedBy": {"uniqueName": "operador@empresa.com"},
        "fields": {
            "System.Description": {
                "newValue": "<p>Tercera versión con texto sustancialmente diferente.</p>",
            }
        },
    }
    result = select_latest_human_edit(
        [_HUMAN_REV_2, rev3],
        baseline_rev=1,
        baseline_author="stacky-svc@example.com",
        service_identities=set(),
        already_processed_revs=set(),
    )
    assert result is not None
    assert result.rev == 3


def test_no_service_identities_no_baseline_author_accepts_human():
    """service_identities vacío + baseline_author=None + rev > baseline_rev → acepta como humana."""
    from harness.ado_edit_detect import is_human_edit
    result = is_human_edit(
        _HUMAN_REV_2,
        baseline_rev=1,
        baseline_author=None,
        service_identities=set(),
    )
    assert result is not None
    assert result.rev == 2


def test_fixture_contract_shape_extractors():
    """Shape crudo real de ADO /updates: los extractores producen (2, 'op@x', '<p>a b...') sin lanzar."""
    from harness.ado_edit_detect import _extract_rev, _extract_author, _extract_body
    assert _extract_rev(_SHAPE_REAL) == 2
    assert _extract_author(_SHAPE_REAL) == "op@x"
    body = _extract_body(_SHAPE_REAL)
    assert "a b" in body

    # Un dict sin fields ni revisedBy → None/"" sin lanzar
    empty = {}
    assert _extract_rev(empty) is None
    assert _extract_author(empty) is None
    assert _extract_body(empty) == ""


def test_human_edit_has_no_author_attribute():
    """HumanEdit NO tiene atributo 'author' — garantiza no-PII por construcción (C4)."""
    from harness.ado_edit_detect import HumanEdit
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(HumanEdit)}
    assert "author" not in field_names
    assert "author_email" not in field_names
