"""Tests para services.agent_env (Fase 3c).

Verifica que build_agent_env() filtra credenciales sensibles antes de pasar
el entorno al subproceso del agente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_ado_pat_is_filtered():
    from services.agent_env import build_agent_env

    base = {
        "PATH": "/usr/bin",
        "HOME": "/home/x",
        "ADO_PAT": "supersecret",
        "AZURE_PAT": "alsosecret",
    }
    out = build_agent_env(base=base)
    assert "ADO_PAT" not in out
    assert "AZURE_PAT" not in out
    assert out["PATH"] == "/usr/bin"
    assert out["HOME"] == "/home/x"


def test_pattern_based_filter():
    from services.agent_env import build_agent_env

    base = {
        "PATH": "/usr/bin",
        "MY_API_KEY": "x",
        "SOME_TOKEN_THING": "y",
        "JIRA_PASSWORD": "z",
        "USER_PRIVATE_KEY_PATH": "/k",
    }
    out = build_agent_env(base=base)
    assert "MY_API_KEY" not in out
    assert "SOME_TOKEN_THING" not in out
    assert "JIRA_PASSWORD" not in out
    assert "USER_PRIVATE_KEY_PATH" not in out
    assert "PATH" in out


def test_allowlist_keeps_path_variants():
    from services.agent_env import build_agent_env

    base = {"PATH": "/usr/bin", "PATHEXT": ".EXE;.BAT"}
    out = build_agent_env(base=base)
    assert out["PATH"] == "/usr/bin"
    assert out["PATHEXT"] == ".EXE;.BAT"


def test_extra_inyecta_variables():
    from services.agent_env import build_agent_env

    base = {"PATH": "/usr/bin", "ADO_PAT": "x"}
    out = build_agent_env(base=base, extra={"STACKY_EXECUTION_ID": "42"})
    assert out["STACKY_EXECUTION_ID"] == "42"
    assert "ADO_PAT" not in out


def test_extra_deny_filtra_adicional():
    from services.agent_env import build_agent_env

    base = {"PATH": "/usr/bin", "INNOCENT_VAR": "v"}
    out = build_agent_env(base=base, extra_deny={"INNOCENT_VAR"})
    assert "INNOCENT_VAR" not in out


def test_is_denied():
    from services.agent_env import is_denied

    assert is_denied("ADO_PAT")
    assert is_denied("My_API_Key")
    assert is_denied("JIRA_TOKEN")
    assert is_denied("BASIC_AUTH")
    assert not is_denied("PATH")
    assert not is_denied("HOME")
    assert not is_denied("LANG")


def test_does_not_mutate_input():
    from services.agent_env import build_agent_env

    base = {"PATH": "/x", "ADO_PAT": "y"}
    snapshot = dict(base)
    build_agent_env(base=base)
    assert base == snapshot
