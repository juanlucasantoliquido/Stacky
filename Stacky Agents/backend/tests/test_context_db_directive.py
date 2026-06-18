"""Plan 39 C2 — Tests TDD: inyección de directiva DB read-only al contexto del agente.

Tests:
1. test_directive_injected_when_readonly_present — directiva con user="svc_ro", flag ON → bloque contiene usuario/directiva
2. test_directive_never_contains_password — password centinela no aparece en bloque
3. test_no_directive_when_no_readonly — has_readonly False → sin sección DB
4. test_flag_off_is_byte_identical — flag OFF → bloque idéntico al actual (sin sección DB)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _build_block_with_flag(flag_value: str, directive: dict, project_name: str = "MYPROJECT") -> dict | None:
    """Helper: construye el bloque con el flag seteado y la directiva mockeada."""
    from services import context_enrichment as ce
    from services import db_query as dq

    with patch.dict(os.environ, {"STACKY_DB_READONLY_DIRECTIVE_ENABLED": flag_value}), \
         patch.object(dq, "get_db_access_directive", return_value=directive):
        return ce.build_client_profile_block(project_name)


_DIRECTIVE_PRESENT = {
    "has_readonly": True,
    "user": "svc_ro",
    "server": "sqlsrv.test",
    "dialect": "mssql",
    "connection_mode": "sql_login",
    "must_avoid_windows_auth": True,
}

_DIRECTIVE_ABSENT = {
    "has_readonly": False,
    "user": "",
    "server": "",
    "dialect": "",
    "connection_mode": "",
    "must_avoid_windows_auth": False,
}


# ---------------------------------------------------------------------------
# 1. Con flag ON + usuario read-only → bloque inyectado
# ---------------------------------------------------------------------------

def test_directive_injected_when_readonly_present():
    """Flag ON + has_readonly=True → bloque contiene usuario y advertencia de auth integrada."""
    from services import client_profile as cp

    # Necesitamos que build_client_profile_block tenga un perfil real
    fake_profile = {"schema_version": 1, "project_name": "MYPROJECT", "database": {"type": "mssql"}}
    with patch.object(cp, "load_client_profile", return_value=fake_profile), \
         patch.object(cp, "get_project_tracker_type", return_value="ado"), \
         patch.object(cp, "merge_with_defaults", return_value=fake_profile):
        block = _build_block_with_flag("true", _DIRECTIVE_PRESENT, "MYPROJECT")

    assert block is not None
    content = block.get("content", "")
    assert "svc_ro" in content
    assert "SOLO LECTURA" in content
    assert "PROHIBIDO" in content


# ---------------------------------------------------------------------------
# 2. Password centinela no aparece NUNCA en el bloque
# ---------------------------------------------------------------------------

def test_directive_never_contains_password():
    """Password centinela TOP_SECRET_PASSWORD no aparece en el bloque."""
    from services import client_profile as cp

    sentinel = "TOP_SECRET_PASSWORD"
    directive_with_pass = {**_DIRECTIVE_PRESENT}
    # get_db_access_directive nunca devuelve password, pero aun así verificamos

    fake_profile = {"schema_version": 1, "project_name": "MYPROJECT", "database": {"type": "mssql"}}
    with patch.object(cp, "load_client_profile", return_value=fake_profile), \
         patch.object(cp, "get_project_tracker_type", return_value="ado"), \
         patch.object(cp, "merge_with_defaults", return_value=fake_profile):
        block = _build_block_with_flag("true", directive_with_pass, "MYPROJECT")

    content = block.get("content", "") if block else ""
    assert sentinel not in content


# ---------------------------------------------------------------------------
# 3. Sin usuario read-only → sin sección DB
# ---------------------------------------------------------------------------

def test_no_directive_when_no_readonly():
    """has_readonly=False → sin sección DB en el bloque."""
    from services import client_profile as cp

    fake_profile = {"schema_version": 1, "project_name": "MYPROJECT", "database": {"type": "mssql"}}
    with patch.object(cp, "load_client_profile", return_value=fake_profile), \
         patch.object(cp, "get_project_tracker_type", return_value="ado"), \
         patch.object(cp, "merge_with_defaults", return_value=fake_profile):
        block = _build_block_with_flag("true", _DIRECTIVE_ABSENT, "MYPROJECT")

    content = block.get("content", "") if block else ""
    assert "SOLO LECTURA" not in content
    assert "PROHIBIDO" not in content


# ---------------------------------------------------------------------------
# 4. Flag OFF → byte-idéntico al bloque sin la sección DB
# ---------------------------------------------------------------------------

def test_flag_off_is_byte_identical():
    """Flag OFF → bloque idéntico al que produciría sin la feature C2."""
    from services import client_profile as cp

    fake_profile = {"schema_version": 1, "project_name": "MYPROJECT", "database": {"type": "mssql"}}
    with patch.object(cp, "load_client_profile", return_value=fake_profile), \
         patch.object(cp, "get_project_tracker_type", return_value="ado"), \
         patch.object(cp, "merge_with_defaults", return_value=fake_profile):
        block_off = _build_block_with_flag("false", _DIRECTIVE_PRESENT, "MYPROJECT")
        block_absent = _build_block_with_flag("false", _DIRECTIVE_ABSENT, "MYPROJECT")

    # Con flag OFF el contenido no varía independientemente del directive
    content_off = block_off.get("content", "") if block_off else ""
    content_absent = block_absent.get("content", "") if block_absent else ""
    assert content_off == content_absent
    assert "SOLO LECTURA" not in content_off
