"""Plan 121 F1 — clase `secrets` determinista en services/egress_policies.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db
from services.egress_policies import check, detect_classes

db.init_db()


def test_detects_github_pat():
    text = "usa este token: ghp_" + "a" * 36
    assert "secrets" in detect_classes(text)


def test_detects_gitlab_pat():
    text = "clave: glpat-" + "abcdEFGH12345678ijkl"
    assert "secrets" in detect_classes(text)


def test_detects_aws_key():
    text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    assert "secrets" in detect_classes(text)


def test_detects_pem_private_key():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    assert "secrets" in detect_classes(text)


def test_detects_jwt():
    text = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    assert "secrets" in detect_classes(text)


def test_detects_password_assignment():
    assert "secrets" in detect_classes("password=hunter22aa")


def test_detects_connection_string():
    text = "Server=db1;Database=x;User Id=sa; password=Sup3rSecreto;"
    assert "secrets" in detect_classes(text)


def test_clean_text_has_no_secrets():
    text = "Este parrafo tecnico describe la arquitectura del modulo sin credenciales."
    assert "secrets" not in detect_classes(text)


def test_check_without_policy_still_allows():
    decision = check(project=None, model="claude", context_text="password=hunter22aa")
    assert decision.allowed is True
    assert "secrets" in decision.detected_classes


def test_existing_classes_untouched():
    assert "pii" in detect_classes("contacto: alguien@ejemplo.com")
