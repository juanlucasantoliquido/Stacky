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


# ===========================================================================
# Plan 284 F0.2 — taxonomía documental (plan vs proyecto)
# ===========================================================================

def test_plan284_classify_doc_path_tabla_completa():
    """Tabla exacta de clasificación, con los casos frontera que hacen fallar
    la regla laxa `^\d{2,3}_` a secas."""
    from services.doc_taxonomy import classify_doc_path

    # Planes / incidentes / checklists numerados
    assert classify_doc_path("docs/137_PLAN_DOCUMENTADOR_V2.md") == "plan"
    assert classify_doc_path("docs/20_INCIDENTE_ADO_241.md") == "plan"
    assert classify_doc_path("docs/25_CHECKLIST_NUEVO_RUNTIME.md") == "plan"

    # Notas canónicas del sistema
    assert classify_doc_path("docs/sistema/01-overview.md") == "system"
    assert classify_doc_path("docs/sistema/13-docs-rag-grafo.md") == "system"
    # La regla 2 (carpeta "sistema") gana sobre la extensión: no es .md y aun así es system.
    assert classify_doc_path("docs/sistema/error_fingerprints.json") == "system"

    # Documentación del proyecto
    assert classify_doc_path("docs/arquitectura.md") == "project"

    # Agentes
    assert classify_doc_path("prompts/Documentador.agent.md") == "agent"

    # Otros
    assert classify_doc_path("README.txt") == "other"
    assert classify_doc_path("") == "other"
    assert classify_doc_path(None) == "other"

    # Caso frontera 1: la regla de carpeta "sistema" tiene PRIORIDAD sobre la
    # de plan numerado. Un archivo que parece plan pero vive en docs/sistema/
    # es documentación canónica y NO debe salir del corpus.
    assert classify_doc_path("docs/sistema/99_PLAN_FALSO.md") == "system"

    # Caso frontera 2: estos 4 archivos EXISTEN de verdad en Stacky Agents/docs/
    # y son documentación DEL PRODUCTO. Con la regla laxa `^\d{2,3}_` caerían
    # como "plan" y sacaríamos del corpus la doc de arquitectura del proyecto:
    # exactamente el bug opuesto al que este plan viene a arreglar.
    assert classify_doc_path("docs/00_VISION.md") == "project"
    assert classify_doc_path("docs/02_ARCHITECTURE.md") == "project"
    assert classify_doc_path("docs/03_DATA_MODEL.md") == "project"
    assert classify_doc_path("docs/14_MANUAL_PARA_AGENTES_WS2.md") == "project"


def test_plan284_summarize_classes_forma_garantizada():
    """El resumen cuenta bien Y devuelve las 5 claves aunque alguna sea 0."""
    from services.doc_taxonomy import DOC_CLASSES, summarize_classes

    paths = [
        "docs/137_PLAN_X.md",          # plan
        "docs/20_INCIDENTE_Y.md",      # plan
        "docs/sistema/01-overview.md",  # system
        "docs/guia.md",                # project
        "docs/00_VISION.md",           # project
    ]
    out = summarize_classes(paths)

    # PRESENCIA: los conteos son los correctos.
    assert out["plan"] == 2
    assert out["system"] == 1
    assert out["project"] == 2

    # AUSENCIA (con su gemelo de presencia): las clases sin ocurrencias siguen
    # estando, en 0 — la forma es garantizada para la UI.
    assert out["agent"] == 0
    assert out["other"] == 0
    assert set(out.keys()) == set(DOC_CLASSES)
    assert len(out) == 5
    # La clasificación es una PARTICIÓN: nada se pierde ni se cuenta dos veces.
    assert sum(out.values()) == len(paths)


# ===========================================================================
# Plan 284 F3 - el gate de citas deja de ser decorativo
# ===========================================================================

def test_plan284_evaluate_citation_gate_tabla():
    """Tabla completa con min_ratio explicito: un test puro no depende del config."""
    from services.doc_documenter import evaluate_citation_gate as g

    # Un doc SIN citas no se rechaza: puede ser legitimamente todo [INF]/[NV].
    r = g({"total": 0, "ok": 0, "bad": []}, min_ratio=0.8)
    assert r["passed"] is True and r["ratio"] == 1.0 and r["reason"] == ""

    r = g({"total": 10, "ok": 10, "bad": []}, min_ratio=0.8)
    assert r["passed"] is True and r["ratio"] == 1.0

    # Frontera exacta: 0.8 >= 0.8 pasa.
    r = g({"total": 10, "ok": 8, "bad": ["a", "b"]}, min_ratio=0.8)
    assert r["passed"] is True

    r = g({"total": 10, "ok": 7, "bad": ["a"]}, min_ratio=0.8)
    assert r["passed"] is False
    assert r["reason"] == "citations_below_threshold:7/10"

    r = g({"total": 1, "ok": 0, "bad": ["x.py:9"]}, min_ratio=0.8)
    assert r["passed"] is False

    # Degradacion: None nunca lanza y no bloquea.
    r = g(None, min_ratio=0.8)
    assert r["passed"] is True
