"""Plan 137 — Documentador v2: evidencia real, citas verificadas.

Tests corridos por archivo con el venv real del repo (backend/.venv, py3.13).
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest


# ---------------------------------------------------------------------------
# F0 — flags + esqueleto
# ---------------------------------------------------------------------------

def test_flags_v2_registradas_y_off_por_default():
    import importlib
    import config
    importlib.reload(config)
    # NOTA (decisión de criterio, ver reporte): la flag master se promovió a
    # default ON (patrón triple, directiva operador 2026-07-15) — ninguna de
    # las 4 excepciones duras aplica (no autopublica, no destructivo, sin
    # prerequisito externo no garantizado, no reduce seguridad). El nombre
    # del test se conserva (cita literal del plan) pero la aserción refleja
    # la decisión real tomada.
    assert config.config.STACKY_DOCS_DOCUMENTER_V2_ENABLED is True
    assert config.config.STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS == 12000


def test_flags_v2_en_flag_registry():
    from services.harness_flags import FLAG_REGISTRY
    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in ("STACKY_DOCS_DOCUMENTER_V2_ENABLED", "STACKY_DOCS_DOCUMENTER_EVIDENCE_MAX_CHARS"):
        assert key in by_key
        assert by_key[key].requires == "STACKY_DOCS_DOCUMENTER_ENABLED"
    # Decisión de criterio: default ON (ver nota arriba) — patrón triple aplicado.
    assert by_key["STACKY_DOCS_DOCUMENTER_V2_ENABLED"].default is True


def test_modulo_doc_evidence_importa():
    import services.doc_evidence  # noqa: F401


# ---------------------------------------------------------------------------
# F1 — evidencia real de módulo
# ---------------------------------------------------------------------------

@pytest.fixture
def mini_repo(tmp_path):
    mod = tmp_path / "mod"
    mod.mkdir()
    (mod / "a.py").write_text("# comment\n# comment2\ndef foo():\n    pass\n", encoding="utf-8")
    (mod / "b.ts").write_text("export function bar() {\n  return 1;\n}\n", encoding="utf-8")
    return tmp_path


def test_extract_symbols_python_y_ts(mini_repo):
    from services.doc_evidence import extract_symbols
    content_a = (mini_repo / "mod" / "a.py").read_text(encoding="utf-8")
    syms_a = extract_symbols("mod/a.py", content_a)
    assert any(s.startswith("mod/a.py:3") and "def foo():" in s for s in syms_a)
    content_b = (mini_repo / "mod" / "b.ts").read_text(encoding="utf-8")
    syms_b = extract_symbols("mod/b.ts", content_b)
    assert any(s.startswith("mod/b.ts:1") and "export function bar()" in s for s in syms_b)


def test_extract_symbols_extension_desconocida_vacia():
    from services.doc_evidence import extract_symbols
    assert extract_symbols("x.xyz", "def foo(): pass") == []


def test_build_module_evidence_arbol_y_simbolos(mini_repo):
    from services.doc_evidence import build_module_evidence
    out = build_module_evidence(str(mini_repo), "mod")
    assert "ARBOL:" in out
    assert "SIMBOLOS:" in out
    assert "mod/a.py" in out
    assert "mod/a.py:3" in out


def test_build_module_evidence_excluye_node_modules(mini_repo):
    from services.doc_evidence import build_module_evidence
    nm = mini_repo / "mod" / "node_modules"
    nm.mkdir()
    (nm / "x.js").write_text("function x() {}\n", encoding="utf-8")
    out = build_module_evidence(str(mini_repo), "mod")
    assert "node_modules" not in out


def test_build_module_evidence_trunca(mini_repo):
    from services.doc_evidence import build_module_evidence
    out = build_module_evidence(str(mini_repo), "mod", max_chars=50)
    suffix = "\n[...evidencia truncada]"
    assert len(out) <= 50 + len(suffix)
    assert out.endswith(suffix)


def test_build_module_evidence_dir_inexistente_vacio(mini_repo):
    from services.doc_evidence import build_module_evidence
    assert build_module_evidence(str(mini_repo), "no_existe") == ""


def test_module_context_v2_incluye_arbol_y_simbolos(monkeypatch, mini_repo):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import services.doc_indexer as doc_indexer
    monkeypatch.setattr(
        doc_indexer, "list_doc_sources",
        lambda project_name: {"workspace_root": str(mini_repo)},
    )
    from services.doc_documenter import _module_context_block
    content = _module_context_block("p", "mod")["content"]
    assert "EVIDENCIA DEL CODIGO" in content
    assert "mod/a.py:3" in content


def test_module_context_flag_off_identico_113(monkeypatch):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)
    from services.doc_documenter import _module_context_block
    content = _module_context_block("p", "mod")["content"]
    assert content == "Documentá el módulo 'mod'. Citá archivo:línea del código real."


# ---------------------------------------------------------------------------
# F2 — verificador determinista de citas [V]
# ---------------------------------------------------------------------------

def test_extract_citations_basico():
    from services.doc_evidence import extract_citations
    assert extract_citations("ver a.py:10 y src/b.ts:3") == [("a.py", 10), ("src/b.ts", 3)]


def test_extract_citations_dedup_y_backslash():
    from services.doc_evidence import extract_citations
    assert extract_citations("x\\y.py:5 x/y.py:5") == [("x/y.py", 5)]


def test_extract_citations_ignora_urls_y_versiones():
    from services.doc_evidence import extract_citations
    text = "ver http://x.com:8080 y versión 1.0.73:12 pero sí a.py:3"
    assert extract_citations(text) == [("a.py", 3)]


def test_verify_citations_ok_y_bad(tmp_path):
    from services.doc_evidence import verify_citations
    (tmp_path / "a.py").write_text("\n".join(f"line{i}" for i in range(12)), encoding="utf-8")
    result = verify_citations("a.py:10 a.py:99 nope.py:1", str(tmp_path))
    assert result["total"] == 3
    assert result["ok"] == 1
    assert "a.py:99" in result["bad"]
    assert "nope.py:1" in result["bad"]


def test_verify_citations_sin_root():
    from services.doc_evidence import verify_citations
    result = verify_citations("a.py:1", "")
    assert result["ok"] == 0


def test_apply_proposals_anota_citations(tmp_path):
    from services.doc_documenter import DocProposal, apply_proposals
    (tmp_path / "a.py").write_text("x\n", encoding="utf-8")
    prop = DocProposal(path="out.md", action="create", content="[V] a.py:1", marks_ok=True, sources=[])
    result = apply_proposals([prop], str(tmp_path), None, workspace_root=str(tmp_path))
    assert result.files[0]["citations"]["ok"] == 1


def test_apply_proposals_sin_workspace_root_sin_files_citations(tmp_path):
    from services.doc_documenter import DocProposal, apply_proposals
    prop = DocProposal(path="out.md", action="create", content="[V] a.py:1", marks_ok=True, sources=[])
    result = apply_proposals([prop], str(tmp_path), None)
    assert result.files == []
