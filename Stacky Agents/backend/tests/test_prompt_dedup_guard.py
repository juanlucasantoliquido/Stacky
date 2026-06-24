"""Guard repo-wide (Plan 69 v3) para no duplicar bloques de identidad."""

from pathlib import Path


_TARGETS = [
    Path("services/codex_cli_runner.py"),
    Path("services/claude_code_cli_runner.py"),
]


def test_dp05_no_duplicated_agent_block_anywhere():
    """El header canónico vive solo en invocation_block."""
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for rel in _TARGETS:
        text = (root / rel).read_text(encoding="utf-8")
        if "## Agente seleccionado\n" in text:
            offenders.append(rel.as_posix())
    assert not offenders, (
        f"Bloque '## Agente seleccionado' duplicado en: {offenders}. "
        "La identidad debe vivir solo en invocation_block."
    )
