"""Plan 39 C0/C1 — Test de resolución de usuario read-only de BD.

Tests TDD (deben pasar DESPUÉS de agregar get_db_access_directive a db_query.py):

1. test_resolve_prefers_payload_user — auth file con user → user=="svc_ro", connection_mode=="sql_login"
2. test_resolve_falls_back_to_hint — auth file sin user, perfil con readonly_user_hint → user=="hint_ro"
3. test_directive_has_readonly_true_and_avoid_windows — has_readonly True, must_avoid_windows_auth True, sin "password"
4. test_directive_no_auth_file_is_safe — sin auth file → has_readonly False, sin lanzar
5. test_directive_never_returns_password — dict no contiene clave "password"
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _mock_profile(user: str = "svc_ro", hint: str = "") -> dict:
    return {
        "database": {
            "server": "sqlsrv.test",
            "type": "mssql",
            "readonly_auth_ref": "auth/db_readonly.json",
            "readonly_user_hint": hint,
        }
    }


# ---------------------------------------------------------------------------
# 1. auth file con user → prioritario, connection_mode=="sql_login"
# ---------------------------------------------------------------------------

def test_resolve_prefers_payload_user():
    """_resolve_db_readonly retorna user del auth file y agrega connection_mode."""
    from services import db_query as dq

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        proj_dir = tmp_path / "MYPROJECT"
        (proj_dir / "auth").mkdir(parents=True)
        auth_data = {"server": "s", "database": "d", "user": "svc_ro", "password": "secret"}
        (proj_dir / "auth" / "db_readonly.json").write_text(json.dumps(auth_data))

        secret = MagicMock()
        secret.value = "secret"

        with patch("project_manager.PROJECTS_DIR", tmp_path), \
             patch.object(dq, "load_client_profile", return_value=_mock_profile()), \
             patch.object(dq, "read_secret_from_file", return_value=secret):
            result = dq._resolve_db_readonly("MYPROJECT")

    assert result.get("user") == "svc_ro"
    assert result.get("connection_mode") == "sql_login"


# ---------------------------------------------------------------------------
# 2. auth file sin user → readonly_user_hint como fallback
# ---------------------------------------------------------------------------

def test_resolve_falls_back_to_hint():
    """Sin user en auth file → usa readonly_user_hint del perfil."""
    from services import db_query as dq

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        proj_dir = tmp_path / "MYPROJECT"
        (proj_dir / "auth").mkdir(parents=True)

        # auth file SIN user
        auth_data = {"server": "s", "database": "d", "password": "secret"}
        (proj_dir / "auth" / "db_readonly.json").write_text(json.dumps(auth_data))

        secret = MagicMock()
        secret.value = "secret"

        with patch("project_manager.PROJECTS_DIR", tmp_path), \
             patch.object(dq, "load_client_profile", return_value=_mock_profile(hint="hint_ro")), \
             patch.object(dq, "read_secret_from_file", return_value=secret):
            result = dq._resolve_db_readonly("MYPROJECT")

    assert result.get("user") == "hint_ro"
    assert result.get("connection_mode") == "sql_login"


# ---------------------------------------------------------------------------
# 3. get_db_access_directive: has_readonly True + must_avoid_windows_auth True
# ---------------------------------------------------------------------------

def test_directive_has_readonly_true_and_avoid_windows():
    """Con auth file válido: has_readonly=True, must_avoid_windows_auth=True."""
    from services import db_query as dq

    resolved = {
        "server": "sqlsrv.test",
        "database": "testdb",
        "user": "svc_ro",
        "password": "s3cr3t",
        "dialect": "mssql",
        "connection_mode": "sql_login",
    }

    with patch.object(dq, "_resolve_db_readonly", return_value=resolved):
        directive = dq.get_db_access_directive("MYPROJECT")

    assert directive["has_readonly"] is True
    assert directive["must_avoid_windows_auth"] is True
    assert "password" not in directive


# ---------------------------------------------------------------------------
# 4. Sin auth file → has_readonly False, sin lanzar
# ---------------------------------------------------------------------------

def test_directive_no_auth_file_is_safe():
    """Sin credencial → has_readonly=False, no lanza."""
    from services import db_query as dq

    with patch.object(dq, "_resolve_db_readonly", return_value={}):
        directive = dq.get_db_access_directive("NOPROJECT")

    assert directive["has_readonly"] is False
    assert directive.get("user") == ""


# ---------------------------------------------------------------------------
# 5. Nunca retorna clave "password"
# ---------------------------------------------------------------------------

def test_directive_never_returns_password():
    """La directiva NUNCA expone el password."""
    from services import db_query as dq

    resolved = {
        "server": "s",
        "database": "d",
        "user": "u",
        "password": "TOP_SECRET",
        "dialect": "mssql",
        "connection_mode": "sql_login",
    }

    with patch.object(dq, "_resolve_db_readonly", return_value=resolved):
        directive = dq.get_db_access_directive("PROJ")

    assert "password" not in directive
    assert "TOP_SECRET" not in str(directive)
