"""
Plan 96 F1 — Clasificador puro de fallos (services/failure_doctor.py).
Catálogo de 12 clases + classify_failure determinista, sin I/O, sin LLM.
"""

import pytest

from services.failure_doctor import FAILURE_PATTERNS, classify_failure


def test_f1_catalog_has_min_12_classes():
    """F1 — El catálogo tiene al menos 12 clases, ids únicos, title/hint no vacíos."""
    assert len(FAILURE_PATTERNS) >= 12
    ids = [p["id"] for p in FAILURE_PATTERNS]
    assert len(ids) == len(set(ids)), "ids del catálogo deben ser únicos"
    for p in FAILURE_PATTERNS:
        assert p["title"], f"{p['id']} sin title"
        assert p["hint"], f"{p['id']} sin hint"


# Fragmentos de log representativos, uno por clase del catálogo.
_LOG_FRAGMENTS = {
    "cmd_not_found": "robocopy: command not found\n##[error]Process completed with exit code 127",
    "file_not_found": "cp: cannot stat 'build/output.zip': No such file or directory",
    "permission_denied": "cp: cannot create regular file '/opt/app/config.json': Permission denied",
    "var_undefined": "##[error]La variable MISSING_VAR no esta definida en este pipeline",
    "auth_failed": "remote: HTTP Basic: Access denied\nfatal: Authentication failed for 'https://dev.azure.com/org/repo'",
    "network": "curl: (6) Could not resolve host: api.example.internal",
    "timeout": "##[error]The job running on agent has exceeded the maximum execution time. Job exceeded the timeout",
    "disk_space": "write error: No space left on device",
    "yaml_config": "##[error]Error parsing template: mapping values are not allowed in this context",
    "test_failures": "FAILED (failures=3)\n17 tests failed, 45 passed",
    "package_manager": "npm ERR! code ERESOLVE\nnpm ERR! Unable to resolve dependency tree",
    "exit_code": "##[error]Process completed with exit code 1",
}


@pytest.mark.parametrize("failure_id", list(_LOG_FRAGMENTS.keys()))
def test_f1_classifies(failure_id):
    """F1 — Cada clase del catálogo se detecta con un fragmento de log real."""
    fragment = _LOG_FRAGMENTS[failure_id]
    log = f"Step 1: setup ok\nStep 2: running build\n{fragment}\nStep 3: cleanup"
    result = classify_failure(log)
    matched_ids = [m["id"] for m in result["matches"]]
    assert failure_id in matched_ids, f"{failure_id} no matcheo. matches={matched_ids}"
    # El snippet debe contener el fragmento del log real (al menos una línea de él).
    first_line_of_fragment = fragment.splitlines()[0]
    assert first_line_of_fragment in result["snippet"], (
        f"snippet no contiene la línea del match para {failure_id}: "
        f"{result['snippet']!r}"
    )


def test_f1_no_match_fallback_tail():
    """F1 — Log sin patrones conocidos ⇒ matches=[] y snippet = últimas líneas."""
    lines = [f"linea normal {i}" for i in range(100)]
    log = "\n".join(lines)
    result = classify_failure(log)
    assert result["matches"] == []
    assert result["snippet"] == "\n".join(lines[-40:])


def test_f1_dedup_and_order():
    """F1 — 2 veces cmd_not_found + 1 file_not_found ⇒ 2 matches en orden de aparición."""
    log = "\n".join([
        "step 1",
        "robocopy: command not found",
        "step 2",
        "cp: cannot stat 'x': No such file or directory",
        "step 3",
        "xcopy: command not found",
    ])
    result = classify_failure(log)
    matched_ids = [m["id"] for m in result["matches"]]
    assert matched_ids == ["cmd_not_found", "file_not_found"], (
        f"esperaba dedup+orden de aparición, obtuve {matched_ids}"
    )


def test_f1_huge_log_tail_only():
    """F1 — Log de >200k chars: solo se analiza el TAIL; un patrón solo al inicio
    NO matchea, uno al final SÍ."""
    head_pattern = "robocopy: command not found\n"  # solo al inicio
    filler = "x" * 250_000  # fuerza truncado del head
    tail_pattern = "\ncp: cannot stat 'y': No such file or directory\n"
    log = head_pattern + filler + tail_pattern

    result = classify_failure(log)
    matched_ids = [m["id"] for m in result["matches"]]
    assert "cmd_not_found" not in matched_ids, "el head truncado no debe matchear"
    assert "file_not_found" in matched_ids, "el patrón del tail debe matchear"


def test_f1_empty_log_safe():
    """F1 — Log vacío ⇒ {'matches': [], 'snippet': ''}, nunca lanza."""
    result = classify_failure("")
    assert result == {"matches": [], "snippet": ""}


def test_f1_pure_no_mutation():
    """F1 — classify_failure es pura: no muta el catálogo ni el input."""
    original_patterns_len = len(FAILURE_PATTERNS)
    log = "robocopy: command not found"
    classify_failure(log)
    classify_failure(log)
    assert len(FAILURE_PATTERNS) == original_patterns_len
    assert log == "robocopy: command not found"
