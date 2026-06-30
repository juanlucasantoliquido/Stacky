"""Plan 49 F5 — Centinela de no-determinismo acotado.

Meta-test estático: prohíbe fuentes de no-determinismo (datetime.now, time.time,
time.monotonic, random.*) dentro de un allowlist EXPLÍCITO de módulos del núcleo
del arnés, salvo seam inyectable o excepción justificada en _JUSTIFIED.

Protege el determinismo del que dependen los golden-sets (F0-F2) y todo el arnés.
"""

import re
import pathlib

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]

# Módulos del núcleo del arnés vigilados (rutas relativas a backend/).
_GUARDED = [
    "contract_validator.py",
    "harness/capabilities.py",
    "harness/complexity.py",
    "harness/criteria_repair.py",
    "harness/exec_repair.py",
    "harness/failure.py",
    "harness/model_policy.py",
    "harness/post_run.py",
    "harness/pricing.py",
    "harness/resume.py",
    "harness/run_contract.py",
    "harness/run_repair.py",
    "harness/runaway_guard.py",
    "harness/telemetry.py",
    "services/claude_code_cli_runner.py",
    "services/codex_cli_runner.py",
]

_FORBIDDEN = [
    re.compile(r"\bdatetime\.now\("),
    re.compile(r"\btime\.time\("),
    re.compile(r"\btime\.monotonic\("),
    re.compile(r"\brandom\.\w"),
]

# (archivo, patron_str) explícitamente justificados (motivo en el valor).
# Los runners CLI miden tiempo REAL de ejecución del subproceso (timeouts de sesión,
# deadlines de runaway/idle, detección de no-eventos). No afecta el CONTENIDO del
# output del agente: es control de proceso, no datos. Por eso es determinismo-seguro.
_JUSTIFIED: dict[tuple[str, str], str] = {
    ("services/codex_cli_runner.py", r"\btime\.monotonic\("):
        "timeout/idle real del subproceso codex, no afecta el output",
    ("services/claude_code_cli_runner.py", r"\btime\.monotonic\("):
        "deadlines de sesión/runaway/idle del subproceso claude, no afecta el output",
    ("services/claude_code_cli_runner.py", r"\btime\.time\("):
        "spawn_epoch para correlación de logs del subproceso, no afecta el output",
}


@pytest.mark.parametrize("rel", _GUARDED, ids=lambda r: r)
def test_no_fuentes_de_no_determinismo(rel):
    path = _BACKEND / rel
    assert path.exists(), f"módulo vigilado inexistente: {rel} (actualizar _GUARDED)"
    src = path.read_text(encoding="utf-8")
    hits = []
    for pat in _FORBIDDEN:
        if pat.search(src) and (rel, pat.pattern) not in _JUSTIFIED:
            hits.append(pat.pattern)
    assert not hits, (
        f"{rel}: fuente(s) de no-determinismo {hits}. "
        "Refactorizar a seam inyectable (recibir now/rng por parámetro) "
        "o agregar a _JUSTIFIED con motivo."
    )
