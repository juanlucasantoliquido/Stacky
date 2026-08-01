"""Plan 137 F3/F4/F5 — pipeline v2 del Documentador: short-circuit, persistencia, preview.

Tests corridos por archivo con el venv real del repo (backend/.venv, py3.13).
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest


# ---------------------------------------------------------------------------
# C9 — fixture anti test-order pollution para _run_registry
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_run_registry():
    from services import doc_documenter
    snapshot = dict(doc_documenter._run_registry)
    yield
    doc_documenter._run_registry.clear()
    doc_documenter._run_registry.update(snapshot)


# ---------------------------------------------------------------------------
# F3 — short-circuit de modos sin targets
# ---------------------------------------------------------------------------

def test_should_invoke_mode_tabla_completa():
    from services.doc_documenter import DocumenterMode, DocumenterPlan, should_invoke_mode

    plan_vacio = DocumenterPlan(
        status="ok", modes=[], notes_to_normalize=[], notes_to_update=[],
    )
    plan_lleno = DocumenterPlan(
        status="ok", modes=[], notes_to_normalize=["a.md"], notes_to_update=["b.md"],
    )

    assert should_invoke_mode(DocumenterMode.NORMALIZAR, plan_vacio, 0) == (False, "sin_notas_para_normalizar")
    assert should_invoke_mode(DocumenterMode.NORMALIZAR, plan_lleno, 0)[0] is True
    assert should_invoke_mode(DocumenterMode.ACTUALIZAR, plan_vacio, 0) == (False, "sin_notas_stale")
    assert should_invoke_mode(DocumenterMode.ACTUALIZAR, plan_lleno, 0)[0] is True
    assert should_invoke_mode(DocumenterMode.ENRIQUECER, plan_vacio, 0) == (False, "sin_huerfanas")
    assert should_invoke_mode(DocumenterMode.ENRIQUECER, plan_vacio, 3)[0] is True
    assert should_invoke_mode(DocumenterMode.RECONSTRUIR, plan_vacio, 0) == (True, "")
    assert should_invoke_mode(DocumenterMode.RECONSTRUIR, plan_lleno, 5) == (True, "")
    assert should_invoke_mode(DocumenterMode.COMPLETAR, plan_vacio, 0) == (True, "")
    assert should_invoke_mode(DocumenterMode.COMPLETAR, plan_lleno, 5) == (True, "")


def test_short_circuit_no_invoca_modos_sin_targets(monkeypatch, tmp_path, clean_run_registry):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)

    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, DocumenterPlan

    plan = DocumenterPlan(
        status="ok", modes=[DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER],
        notes_to_normalize=[], notes_to_update=[],
    )
    monkeypatch.setattr(doc_documenter, "plan_documenter_run", lambda *a, **k: plan)
    monkeypatch.setattr(
        doc_documenter, "_resolve_target_paths",
        lambda project_name: (str(tmp_path), str(tmp_path), str(tmp_path)),
    )

    import services.doc_graph as doc_graph
    monkeypatch.setattr(doc_graph, "build_graph", lambda project_name=None, **kwargs: {"orphans": []})

    invoked: list[str] = []

    def _spy_invoke(mode, ctx, project_name, runtime, **kwargs):
        invoked.append(str(mode.value))
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _spy_invoke)

    report = doc_documenter.run_documenter("p", "mock")

    assert invoked == []
    assert report["modes_skipped"] == [
        {"mode": "NORMALIZAR", "reason": "sin_notas_para_normalizar"},
        {"mode": "ENRIQUECER", "reason": "sin_huerfanas"},
    ]


def test_flag_off_invoca_todos_los_modos(monkeypatch, tmp_path, clean_run_registry):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)

    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, DocumenterPlan

    plan = DocumenterPlan(
        status="ok", modes=[DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER],
        notes_to_normalize=[], notes_to_update=[],
    )
    monkeypatch.setattr(doc_documenter, "plan_documenter_run", lambda *a, **k: plan)
    monkeypatch.setattr(
        doc_documenter, "_resolve_target_paths",
        lambda project_name: (str(tmp_path), str(tmp_path), str(tmp_path)),
    )

    invoked: list[str] = []

    def _spy_invoke(mode, ctx, project_name, runtime, **kwargs):
        invoked.append(str(mode.value))
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _spy_invoke)

    report = doc_documenter.run_documenter("p", "mock")

    assert invoked == ["NORMALIZAR", "ENRIQUECER"]
    assert report["modes_skipped"] == []


# ---------------------------------------------------------------------------
# F4 — historial persistente de corridas
# ---------------------------------------------------------------------------

def test_persist_y_get_run_desde_disco(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("abc123", {
        "state": "completed", "written": [], "skipped": [], "modes": [],
        "branch": None, "degraded": True,
    })
    rec = doc_documenter.get_run("abc123")
    assert rec is not None
    assert rec["state"] == "completed"


def test_list_runs_ordena_y_limita(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    for i, run_id in enumerate(["r1", "r2", "r3"]):
        doc_documenter._persist_run_report(run_id, {
            "state": "completed", "written": [], "skipped": [], "modes": [],
            "branch": None, "degraded": False,
        })
        path = doc_documenter._runs_dir() / f"{run_id}.json"
        os.utime(path, (1000 + i * 10, 1000 + i * 10))

    runs = doc_documenter.list_runs(2)
    assert len(runs) == 2
    assert runs[0]["run_id"] == "r3"


def test_persistencia_flag_off_inerte(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("x1", {"state": "completed"})
    assert doc_documenter.list_runs() == []
    assert not (tmp_path / "documenter_runs" / "x1.json").exists()


def test_persist_es_upsert(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("r1", {"state": "running", "written": [], "skipped": [], "modes": []})
    doc_documenter._persist_run_report("r1", {"state": "completed", "written": [], "skipped": [], "modes": []})
    files = list(doc_documenter._runs_dir().glob("r1.json"))
    assert len(files) == 1
    assert doc_documenter.get_run("r1")["state"] == "completed"


def test_retencion_100(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    for i in range(102):
        doc_documenter._persist_run_report(f"r{i}", {
            "state": "completed", "written": [], "skipped": [], "modes": [],
        })
    remaining = list(doc_documenter._runs_dir().glob("*.json"))
    assert len(remaining) == 100


def test_list_runs_agrega_citas(monkeypatch, tmp_path):
    # A1 — list_runs() agrega citations_ok/citations_total sumando por archivo.
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("rcit", {
        "state": "completed", "written": [], "skipped": [], "modes": [],
        "branch": None, "degraded": False,
        "files": [
            {"citations": {"total": 3, "ok": 2, "bad": ["x"]}},
            {"citations": {"total": 1, "ok": 1, "bad": []}},
        ],
    })
    runs = doc_documenter.list_runs()
    assert len(runs) == 1
    assert runs[0]["citations_ok"] == 3
    assert runs[0]["citations_total"] == 4


# ---------------------------------------------------------------------------
# F5 — preview por archivo en el reporte
# ---------------------------------------------------------------------------

def test_apply_proposals_incluye_preview(tmp_path):
    from services.doc_documenter import DocProposal, apply_proposals
    long_content = "x" * 5000
    prop = DocProposal(path="out.md", action="create", content=long_content,
                       marks_ok=True, sources=[])
    result = apply_proposals([prop], str(tmp_path), None, workspace_root=str(tmp_path))
    assert len(result.files[0]["content_preview"]) == 4000


# ===========================================================================
# Plan 284 F1 — frontera dura PLANES vs PROYECTO
# ===========================================================================

def _iter_file_nodes(nodes):
    """Recorre recursivamente y devuelve solo los nodos de ARCHIVO."""
    for n in nodes:
        if n.get("kind") == "folder":
            yield from _iter_file_nodes(n.get("children", []))
        else:
            yield n


def test_plan284_index_node_lleva_doc_class(monkeypatch):
    """Con la flag ON, todo nodo de archivo trae doc_class, y aparecen las dos
    clases que importan (plan y system)."""
    from config import config
    from services import doc_indexer

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", True)
    doc_indexer.invalidate_cache()  # el índice se cachea 300s: sin esto leemos el árbol viejo

    roots = doc_indexer._index_technical_docs()
    files = list(_iter_file_nodes(roots))

    # AUSENCIA: ningún nodo de archivo sin doc_class (ni ausente ni None).
    assert files, "el árbol técnico no debería estar vacío"
    for n in files:
        assert "doc_class" in n, f"nodo sin doc_class: {n.get('path')}"
        assert n["doc_class"] is not None

    # PRESENCIA: las dos clases que este plan viene a separar existen de verdad.
    clases = {n["doc_class"] for n in files}
    assert "plan" in clases, f"no se detectó ningún plan; clases vistas: {clases}"
    assert "system" in clases, f"no se detectó ninguna nota de sistema; clases: {clases}"

    doc_indexer.invalidate_cache()


def test_plan284_doc_class_inerte_con_flag_off(monkeypatch):
    """Con la flag OFF el campo queda inerte ("") pero el árbol SIGUE teniendo
    nodos: si estuviera vacío, el assert de ausencia pasaría por accidente."""
    from config import config
    from services import doc_indexer

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", False)
    doc_indexer.invalidate_cache()

    roots = doc_indexer._index_technical_docs()
    files = list(_iter_file_nodes(roots))

    # PRESENCIA de control: hay nodos que inspeccionar.
    assert len(files) > 0, "sin nodos el assert de ausencia sería un falso verde"
    # AUSENCIA: ninguno trae clasificación.
    for n in files:
        assert n.get("doc_class") == "", f"{n.get('path')} debería estar inerte"

    doc_indexer.invalidate_cache()


def test_plan284_rag_excluye_planes(monkeypatch, tmp_path):
    """El corpus RAG deja de tragarse los documentos de plan."""
    from config import config
    from services import docs_rag

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", True)

    docs = tmp_path / "docs"
    (docs / "sistema").mkdir(parents=True)
    (docs / "137_PLAN_X.md").write_text("# Plan X\n\nContenido del plan.\n", encoding="utf-8")
    (docs / "sistema" / "01-overview.md").write_text("# Overview\n\nNota canónica.\n", encoding="utf-8")
    (docs / "guia.md").write_text("# Guia\n\nDoc del proyecto.\n", encoding="utf-8")

    # Capturamos qué archivos llegan al troceador: es el punto exacto donde se
    # ve el efecto del filtro. Y neutralizamos la escritura en DB (este test
    # verifica el filtro, no la persistencia).
    import contextlib

    indexados: list[str] = []
    _real_split = docs_rag._split_markdown_to_chunks

    def _spy_split(content, rel_path):
        indexados.append(str(rel_path))
        return _real_split(content, rel_path)

    class _NoopSession:
        def query(self, *a, **k):
            return self

        def filter_by(self, *a, **k):
            return self

        def delete(self, *a, **k):
            return 0

        def add(self, *a, **k):
            return None

    @contextlib.contextmanager
    def _fake_scope():
        yield _NoopSession()

    monkeypatch.setattr(docs_rag, "_split_markdown_to_chunks", _spy_split)
    monkeypatch.setattr(docs_rag, "session_scope", _fake_scope)

    res = docs_rag.index_project("P", str(tmp_path), docs_subpath="docs")
    # PRESENCIA de control: el barrido corrió de verdad sobre archivos reales.
    assert res["files_scanned"] == 2, f"debía escanear 2 de 3 archivos: {res}"

    unidos = " | ".join(indexados)
    # PRESENCIA: la doc real del proyecto sí se indexa.
    assert "01-overview.md" in unidos, f"faltó la nota de sistema: {unidos}"
    assert "guia.md" in unidos, f"faltó la doc de proyecto: {unidos}"
    # AUSENCIA: el plan queda afuera.
    assert "137_PLAN_X.md" not in unidos, f"el plan contaminó el corpus: {unidos}"


def test_plan284_salud_ignora_planes(monkeypatch):
    """La flag gobierna el filtro: con ON los planes no mueven el
    frontmatter_ratio; con OFF sí lo mueven (prueba que el filtro está vivo)."""
    from config import config
    from services import doc_graph, doc_indexer

    prefix = doc_indexer.PROJECT_DOC_SOURCE_PREFIX

    def _nota(path, doc_class, fm):
        return {"kind": "note", "source_id": f"{prefix}x", "path": path,
                "doc_class": doc_class, "has_frontmatter": fm}

    base = [_nota("docs/a.md", "project", True), _nota("docs/b.md", "project", True)]
    planes = [_nota(f"docs/{i}0_PLAN_X.md", "plan", False) for i in range(1, 6)]
    edges = [{"kind": "wikilink"}]

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", True)
    con_on_sin = doc_graph.classify_doc_health(base, edges, None)
    con_on_con = doc_graph.classify_doc_health(base + planes, edges, None)
    assert con_on_sin["frontmatter_ratio"] == con_on_con["frontmatter_ratio"], (
        "con la flag ON los 5 planes no deberían mover el ratio")

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", False)
    con_off_sin = doc_graph.classify_doc_health(base, edges, None)
    con_off_con = doc_graph.classify_doc_health(base + planes, edges, None)
    assert con_off_sin["frontmatter_ratio"] != con_off_con["frontmatter_ratio"], (
        "con la flag OFF los planes SÍ deben contaminar: si no, el filtro no está vivo")


# ===========================================================================
# Plan 284 F2 - la nota del operador llega al prompt
# ===========================================================================

def _plan_enriquecer():
    from services.doc_documenter import DocumenterPlan
    return DocumenterPlan(status="SANA", modes=[], notes_to_normalize=[],
                          notes_to_update=[])


def _stub_run_documenter(monkeypatch, tmp_path):
    """Neutraliza git, salud y persistencia para poder ejercitar el cable."""
    from services import doc_documenter
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "sg", "kind": "sg", "title": "SG", "content": "x"})
    monkeypatch.setattr(doc_documenter, "prepare_doc_branch",
                        lambda *a, **k: (str(tmp_path), None, "rama", False))
    monkeypatch.setattr(doc_documenter, "_health_for_root",
                        lambda *a, **k: {"status": "SANA", "reasons": [],
                                         "frontmatter_ratio": 0.0,
                                         "wikilink_edges": 0, "uncovered_modules": []})
    monkeypatch.setattr(doc_documenter, "_persist_run_report", lambda *a, **k: None)


def _stub_plan(monkeypatch):
    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, DocumenterPlan
    monkeypatch.setattr(doc_documenter, "plan_documenter_run",
                        lambda *a, **k: DocumenterPlan(
                            status="SANA", modes=[DocumenterMode.ENRIQUECER],
                            notes_to_normalize=[], notes_to_update=[], reason="test"))


def test_plan284_nota_del_operador_llega_al_prompt(monkeypatch):
    """El centinela aparece en el TEXTO real del prompt, no solo en el dict."""
    from config import config
    from prompt_builder import render_blocks
    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, build_context_for_mode

    monkeypatch.setattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", True)
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "sg", "kind": "sg", "title": "SG", "content": "x"})

    blocks = build_context_for_mode(DocumenterMode.ENRIQUECER, _plan_enriquecer(),
                                    "P", "NOTA_SENTINELA_284")
    texto = render_blocks(blocks)

    assert "NOTA_SENTINELA_284" in texto
    assert "INDICACIONES DEL OPERADOR" in texto
    assert blocks[0]["id"] == "operator-note"
    # PRESENCIA de control: el bloque canonico sigue ahi (el render no esta vacio).
    assert "docs/sistema/" in texto


def test_plan284_nota_vacia_no_agrega_bloque(monkeypatch):
    from config import config
    from prompt_builder import render_blocks
    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, build_context_for_mode

    monkeypatch.setattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", True)
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "sg", "kind": "sg", "title": "SG", "content": "x"})

    base = build_context_for_mode(DocumenterMode.ENRIQUECER, _plan_enriquecer(), "P")
    for vacia in ("", "   "):
        blocks = build_context_for_mode(DocumenterMode.ENRIQUECER, _plan_enriquecer(),
                                        "P", vacia)
        assert len(blocks) == len(base)
        assert not any(b.get("id") == "operator-note" for b in blocks)
        assert "docs/sistema/" in render_blocks(blocks)


def test_plan284_nota_inerte_con_flag_off(monkeypatch):
    from config import config
    from prompt_builder import render_blocks
    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, build_context_for_mode

    monkeypatch.setattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", False)
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "sg", "kind": "sg", "title": "SG", "content": "x"})

    blocks = build_context_for_mode(DocumenterMode.ENRIQUECER, _plan_enriquecer(),
                                    "P", "NO_DEBE_APARECER_284")
    texto = render_blocks(blocks)
    assert "NO_DEBE_APARECER_284" not in texto
    assert "docs/sistema/" in texto


def test_plan284_nota_viaja_de_run_documenter_al_prompt(monkeypatch, tmp_path,
                                                        clean_run_registry):
    """[GATE REAL DE F2] El cable completo: run_documenter -> build_context_for_mode.

    El censo AST solo prueba que _operator_note_block se llama DENTRO de
    build_context_for_mode. No prueba los otros saltos de la cadena. Un
    operator_note que se persiste en el reporte y nunca se pasa hacia abajo
    satisface todos los demas tests y aun asi jamas llega al modelo: es la
    deuda numero 1 de este repo (construido, testeado, verde y jamas cableado).
    """
    from config import config
    from prompt_builder import render_blocks
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)

    capturado = {}

    def _fake_invoke(mode, context_blocks, project_name, runtime, **kw):
        capturado["blocks"] = context_blocks
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _fake_invoke)
    _stub_plan(monkeypatch)
    _stub_run_documenter(monkeypatch, tmp_path)

    doc_documenter.run_documenter("P", "claude_code_cli",
                                  operator_note="CENTINELA_CABLE_284")

    # PRESENCIA de control: el monkeypatch engancho y hubo bloques de verdad.
    assert capturado.get("blocks"), (
        "invoke_documenter no fue llamada: el assert siguiente seria un falso verde")
    # LO QUE IMPORTA: la nota llego al texto que ve el modelo.
    assert "CENTINELA_CABLE_284" in render_blocks(capturado["blocks"])

    # AUSENCIA GEMELA: sin nota, el centinela no esta pero SIGUE habiendo bloques.
    capturado.clear()
    doc_documenter.run_documenter("P", "claude_code_cli", operator_note="")
    assert capturado.get("blocks"), (
        "sin bloques, el assert de ausencia pasaria por accidente")
    assert "CENTINELA_CABLE_284" not in render_blocks(capturado["blocks"])


def test_plan284_nota_se_persiste_en_el_reporte(monkeypatch, tmp_path,
                                                clean_run_registry):
    from config import config
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_OPERATOR_NOTE_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    _stub_plan(monkeypatch)
    _stub_run_documenter(monkeypatch, tmp_path)

    report = doc_documenter.run_documenter("P", "claude_code_cli", operator_note="hola")
    assert report["operator_note"] == "hola"
