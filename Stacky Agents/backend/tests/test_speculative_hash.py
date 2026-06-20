"""Plan 57 F1 — Tests TDD para compute_key con parámetros runtime/model/effort."""
import pytest
from services.output_cache import compute_key


def _blocks():
    return [{"kind": "story", "content": "test context"}]


def test_same_context_different_runtime_different_hash():
    """Mismo contexto, diferente runtime → hashes distintos."""
    h1 = compute_key(agent_type="business", blocks=_blocks(), runtime="claude_code_cli")
    h2 = compute_key(agent_type="business", blocks=_blocks(), runtime="codex_cli")
    assert h1 != h2


def test_same_context_same_runtime_same_hash():
    """Mismo contexto + mismo runtime → hash idéntico (determinista)."""
    h1 = compute_key(agent_type="business", blocks=_blocks(), runtime="claude_code_cli")
    h2 = compute_key(agent_type="business", blocks=_blocks(), runtime="claude_code_cli")
    assert h1 == h2


def test_empty_string_deterministic():
    """Strings vacíos (default) → hash determinista."""
    h1 = compute_key(agent_type="business", blocks=_blocks(), runtime="")
    h2 = compute_key(agent_type="business", blocks=_blocks(), runtime="")
    assert h1 == h2


def test_runtime_model_effort_combinations():
    """Combinaciones de runtime+model+effort producen hashes únicos."""
    params = [
        dict(runtime="claude_code_cli", model="claude-sonnet-4-6", effort="high"),
        dict(runtime="claude_code_cli", model="claude-sonnet-4-6", effort="low"),
        dict(runtime="claude_code_cli", model="claude-opus-4-8", effort="high"),
        dict(runtime="codex_cli", model="claude-sonnet-4-6", effort="high"),
        dict(runtime="github_copilot", model="", effort=""),
    ]
    hashes = [compute_key(agent_type="business", blocks=_blocks(), **p) for p in params]
    assert len(set(hashes)) == len(hashes), "Combinaciones deben producir hashes únicos"


def test_backward_compat_empty_params_equals_no_params():
    """compute_key sin parámetros extra equivale a pasar strings vacíos."""
    h_old = compute_key(agent_type="business", blocks=_blocks())
    h_new = compute_key(agent_type="business", blocks=_blocks(), runtime="", model="", effort="")
    assert h_old == h_new, "Compatibilidad backward: defaults vacíos = no pasar parámetros"


def test_model_alone_changes_hash():
    """Solo cambiar model cambia el hash."""
    h1 = compute_key(agent_type="business", blocks=_blocks(), model="claude-sonnet-4-6")
    h2 = compute_key(agent_type="business", blocks=_blocks(), model="claude-opus-4-8")
    assert h1 != h2


def test_effort_alone_changes_hash():
    """Solo cambiar effort cambia el hash."""
    h1 = compute_key(agent_type="business", blocks=_blocks(), effort="high")
    h2 = compute_key(agent_type="business", blocks=_blocks(), effort="low")
    assert h1 != h2
