"""Plan 37 — el fallo del CLI se VE (stderr persistido) y la sesión tiene cap.

F2.2 — el motivo real del exit!=0 (stderr) se ensambla en el error persistible.
F3.1 — CLAUDE_CODE_CLI_TIMEOUT tiene un default finito (no 0/ilimitado) para
       que un run colgado no quede zombie ("sin límite de sesión").

Tests unitarios puros sobre los helpers + el default de config (sin spawn de
proceso, barato y determinista).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# F2.2 — stderr se persiste en el mensaje de error (deja de "fallar en silencio")
# ---------------------------------------------------------------------------

def test_stderr_excerpt_keeps_last_lines_and_strips():
    from services import claude_code_cli_runner as r

    lines = [f"línea {i}\n" for i in range(60)]
    excerpt = r._stderr_excerpt(lines, max_lines=40)
    # Solo las últimas 40, sin trailing newline.
    assert excerpt.startswith("línea 20")
    assert excerpt.endswith("línea 59")
    assert "línea 19" not in excerpt
    assert not excerpt.endswith("\n")


def test_stderr_excerpt_empty_when_no_stderr():
    from services import claude_code_cli_runner as r

    assert r._stderr_excerpt([]) == ""


def test_format_cli_error_includes_stderr_when_present():
    from services import claude_code_cli_runner as r

    msg = r._format_cli_error(1, "Error: unknown option --effort")
    assert msg == "claude code cli exited with code 1: Error: unknown option --effort"


def test_format_cli_error_generic_when_no_stderr():
    from services import claude_code_cli_runner as r

    # Sin stderr → mensaje genérico, comportamiento previo intacto.
    assert r._format_cli_error(1, "") == "claude code cli exited with code 1"


def test_format_cli_error_truncates_long_stderr():
    from services import claude_code_cli_runner as r

    msg = r._format_cli_error(2, "x" * 1000)
    # Prefijo + 500 chars de stderr como máximo.
    assert msg.startswith("claude code cli exited with code 2: ")
    assert len(msg) <= len("claude code cli exited with code 2: ") + 500


# ---------------------------------------------------------------------------
# F3.1 — cap de sesión finito por default (no más runs zombie sin límite)
# ---------------------------------------------------------------------------

def test_cli_timeout_default_is_finite():
    from config import config

    # 0 = ilimitado (opt-in). El default debe ser un cap positivo y acotado.
    assert config.CLAUDE_CODE_CLI_TIMEOUT > 0
    assert config.CLAUDE_CODE_CLI_TIMEOUT == 1800
