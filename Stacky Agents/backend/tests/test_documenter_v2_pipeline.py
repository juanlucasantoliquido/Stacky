"""Plan 137 F3/F4/F5 — pipeline v2 del Documentador: short-circuit, persistencia, preview.

Tests corridos por archivo con el venv real del repo (backend/.venv, py3.13).
"""
from __future__ import annotations

import os
import pathlib

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
    # Plan 284 — este test es del short-circuit de MODOS, ortogonal al pipeline
    # de etapas. Se fija la flag explícitamente en vez de depender del default:
    # con las etapas ON el run se detiene en awaiting_approval antes de llegar
    # a los modos, y el test mediría otra cosa.
    monkeypatch.setattr(config.config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)

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
    # Plan 284 — ver la nota del test anterior: se fija la flag de etapas para
    # que este test siga midiendo la invocación de modos y no el gate humano.
    monkeypatch.setattr(config.config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)

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


# ===========================================================================
# Plan 284 F3 - el archivo con citas falsas NO EXISTE EN DISCO
# ===========================================================================

def _props_buena_y_mala():
    from services.doc_documenter import DocProposal
    buena = DocProposal(path="buena.md", action="create",
                        content="[V] real.py:2 documentado", marks_ok=True, sources=[])
    mala = DocProposal(path="mala.md", action="create",
                       content="[V] real.py:999 y [V] inexistente.py:1",
                       marks_ok=True, sources=[])
    return buena, mala


def test_plan284_gate_no_escribe_el_archivo_con_citas_falsas(monkeypatch, tmp_path):
    """Lo que hoy falla: el archivo malo se escribia igual y se reportaba despues."""
    from config import config
    from services.doc_documenter import apply_proposals

    monkeypatch.setattr(config, "STACKY_DOCS_CITATION_GATE_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_CITATION_GATE_MIN_RATIO", 0.8)

    (tmp_path / "real.py").write_text("a\nb\nc\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    buena, mala = _props_buena_y_mala()
    result = apply_proposals([buena, mala], str(out), None,
                             workspace_root=str(tmp_path))

    # PRESENCIA: el archivo con citas validas si se escribe.
    assert "buena.md" in result.written
    assert (out / "buena.md").is_file()

    # AUSENCIA: el archivo con citas falsas NO EXISTE EN DISCO.
    assert "mala.md" not in result.written
    assert not (out / "mala.md").exists()
    assert ("mala.md", "citations_below_threshold:0/2") in result.skipped


def test_plan284_gate_off_conserva_comportamiento_137(monkeypatch, tmp_path):
    """Backward-compat exacta: con el gate OFF se escriben AMBOS archivos."""
    from config import config
    from services.doc_documenter import apply_proposals

    monkeypatch.setattr(config, "STACKY_DOCS_CITATION_GATE_ENABLED", False)

    (tmp_path / "real.py").write_text("a\nb\nc\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    buena, mala = _props_buena_y_mala()
    result = apply_proposals([buena, mala], str(out), None,
                             workspace_root=str(tmp_path))

    assert "buena.md" in result.written and "mala.md" in result.written
    assert (out / "mala.md").is_file()
    # result.files sigue trayendo el conteo de citas (comportamiento del 137).
    assert result.files and all("citations" in f for f in result.files)


def test_plan284_doc_sin_citas_no_se_rechaza(monkeypatch, tmp_path):
    """El que miente es el que cita mal, no el que no cita."""
    from config import config
    from services.doc_documenter import DocProposal, apply_proposals

    monkeypatch.setattr(config, "STACKY_DOCS_CITATION_GATE_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_CITATION_GATE_MIN_RATIO", 0.8)

    out = tmp_path / "out"
    out.mkdir()
    prop = DocProposal(path="sincitas.md", action="create",
                       content="[INF] esto es inferido y [NV] esto no es verificable",
                       marks_ok=True, sources=[])
    result = apply_proposals([prop], str(out), None, workspace_root=str(tmp_path))

    assert "sincitas.md" in result.written
    assert (out / "sincitas.md").is_file()


# ===========================================================================
# Plan 284 F4 - mineria del corpus de tickets con triage auditable
# ===========================================================================

def _clasificar(**kw):
    from services.doc_ticket_mining import classify_ticket
    base = dict(ticket_id=1, ado_id=1001, external_id=1001,
                tracker_type="azure_devops", title="t" * 20,
                description="d" * 250, ado_state="Active", work_item_type="Task")
    base.update(kw)
    return classify_ticket(**base)


def test_plan284_classify_ticket_tabla():
    """Tabla con TODOS los campos fijados y el score exacto de cada fila.

    La v1 decia cosas como 'demo con descripcion larga -> noise (score 3-3=0)':
    esa aritmetica solo cierra si la descripcion esta entre 200 y 799 y el tipo
    no es Task. Con 1200 chars el score da 2 => signal y el test sale rojo. El
    riesgo real no es el rojo: es que alguien 'arregle' el test debilitando el
    assert. Por eso cada fila fija todos los campos.
    """
    # 1 - epica rica: +2 extensa +1 suficiente +1 titulo +1 Epic = 5
    v = _clasificar(ticket_id=1, description="d" * 1200, title="t" * 40, work_item_type="Epic")
    assert (v.score, v.verdict) == (5, "signal")

    # 2 - frontera signal: +1 suficiente +1 titulo = 2
    v = _clasificar(ticket_id=2, description="d" * 250, title="t" * 20, work_item_type="Task")
    assert (v.score, v.verdict) == (2, "signal")

    # 3 - frontera noise: 199 chars no llega a suficiente => +1 titulo = 1
    v = _clasificar(ticket_id=3, description="d" * 199, title="t" * 20, work_item_type="Task")
    assert (v.score, v.verdict) == (1, "noise")

    # 4 - sin descripcion: +1 titulo -2 sin_descripcion = -1
    v = _clasificar(ticket_id=4, description="", title="t" * 20, work_item_type="Task")
    assert (v.score, v.verdict) == (-1, "noise")
    assert "sin_descripcion" in v.reasons

    # 5 - tracker sintetico: +1 suficiente +1 titulo +1 Epic -3 demo = 0
    v = _clasificar(ticket_id=5, tracker_type="demo", description="d" * 300,
                    title="t" * 20, work_item_type="Epic")
    assert (v.score, v.verdict) == (0, "noise")
    assert "tracker_sintetico" in v.reasons

    # 6 - FIX C3: ado_id=-2 y external_id=-7. La regla vieja miraba external_id
    #     contra un frozenset de ado_ids y no lo detectaba.
    v = _clasificar(ticket_id=6, ado_id=-2, external_id=-7, description="d" * 300,
                    title="t" * 20, work_item_type="Epic")
    assert (v.score, v.verdict) == (0, "noise")
    assert "ticket_interno_de_stacky" in v.reasons

    # 7 - titulo ruido: +1 suficiente -2 ruido = -1 (titulo "test" no llega a 15)
    v = _clasificar(ticket_id=7, title="test", description="d" * 300, work_item_type="Task")
    assert (v.score, v.verdict) == (-1, "noise")
    assert "titulo_ruido" in v.reasons

    # 8 - MULTIPROVEEDOR: gitlab no queda en desventaja frente a ADO.
    v = _clasificar(ticket_id=8, tracker_type="gitlab", description="d" * 1200,
                    title="t" * 40, work_item_type="Issue", ado_state="opened")
    assert (v.score, v.verdict) == (5, "signal")

    # 9 - FIX C13: cerrado Y documentado es la MEJOR historia: 5 + 1 = 6
    v = _clasificar(ticket_id=9, description="d" * 1200, title="t" * 40,
                    work_item_type="Epic", ado_state="Done")
    assert (v.score, v.verdict) == (6, "signal")
    assert any(r.startswith("cerrado_y_documentado") for r in v.reasons)

    # 10 - FIX C13: cerrado y flaco = el "obsoleto" del pedido. +1 titulo -2 = -1
    v = _clasificar(ticket_id=10, description="d" * 50, title="t" * 20,
                    work_item_type="Task", ado_state="Done")
    assert (v.score, v.verdict) == (-1, "noise")
    assert any(r.startswith("cerrado_sin_contenido") for r in v.reasons)


def test_plan284_es_sintetico_cubre_los_103():
    """Cualquier id negativo es sintetico: aritmetica, no catalogo."""
    from services.doc_ticket_mining import _es_sintetico

    # PRESENCIA: los detecta.
    assert _es_sintetico(-2, -7) is True
    assert _es_sintetico(-4, -123) is True
    assert _es_sintetico(None, -5) is True
    # AUSENCIA: no marca de mas.
    assert _es_sintetico(1001, 1001) is False
    assert _es_sintetico(None, None) is False
    # No lanza ante basura.
    assert _es_sintetico("x", None) is False


def test_plan284_mine_project_tickets_forma_garantizada(monkeypatch):
    """Con la flag OFF: las 9 claves presentes, enabled=False y ceros.

    Plan 285 F3.1 — eran 8. Se suma `total_rows` porque el bloque de contexto
    no puede declarar el truncamiento sin saber CUANTOS tickets faltaron: hoy
    total_rows se calculaba (doc_ticket_mining.py:190), se usaba solo para el
    booleano `truncated` y se descartaba, y el prompt afirmaba "Se barrieron N
    tickets" con N YA recortado por el cap. La forma sigue siendo GARANTIZADA
    (misma clave en el camino OFF, en el OK y en el except).
    """
    from config import config
    from services.doc_ticket_mining import mine_project_tickets

    monkeypatch.setattr(config, "STACKY_DOCS_TICKET_MINING_ENABLED", False)
    out = mine_project_tickets("P")

    esperadas = {"enabled", "scope", "total", "signal", "noise",
                 "by_tracker", "verdicts", "total_rows", "truncated"}
    assert set(out.keys()) == esperadas          # PRESENCIA de la forma
    assert out["enabled"] is False               # AUSENCIA de datos
    assert out["total"] == 0 and out["verdicts"] == []


def test_plan284_scope_project_es_case_insensitive(monkeypatch):
    """FIX C24: 'p' y 'P' son el MISMO proyecto partido por case-sensitivity."""
    from config import config
    from db import session_scope
    from models import Ticket
    from services.doc_ticket_mining import mine_project_tickets

    monkeypatch.setattr(config, "STACKY_DOCS_TICKET_MINING_ENABLED", True)

    import db as _db
    from sqlalchemy import inspect as _inspect
    if not _inspect(_db.engine).has_table("tickets"):
        Ticket.__table__.create(bind=_db.engine, checkfirst=True)

    with session_scope() as s:
        s.query(Ticket).delete()
        for i, proj in enumerate(["p", "p", "P", "P", "OTRO"]):
            s.add(Ticket(ado_id=9000 + i, external_id=9000 + i,
                         project=proj, stacky_project_name=proj,
                         tracker_type="azure_devops",
                         title="t" * 20, description="d" * 300,
                         ado_state="Active", work_item_type="Task"))

    out = mine_project_tickets("P", scope="project")
    assert out["total"] == 4, f"case-insensitive roto: {out['total']}"   # PRESENCIA

    # AUSENCIA GEMELA: el ticket de OTRO proyecto no entra.
    titulos = {v.ticket_id for v in out["verdicts"]}
    otro = mine_project_tickets("OTRO", scope="project")
    assert otro["total"] == 1
    assert not (titulos & {v.ticket_id for v in otro["verdicts"]})

    with session_scope() as s:
        s.query(Ticket).delete()


def test_plan284_build_tickets_block_solo_signal():
    """El bloque lleva los signal y NO lleva los noise."""
    from services.doc_ticket_mining import TicketVerdict, build_tickets_context_block

    def _v(i, verdict, titulo):
        return TicketVerdict(ticket_id=i, external_id=i, tracker_type="azure_devops",
                             title=titulo, verdict=verdict, reasons=["r"], score=0)

    mining = {"total": 5, "noise": 3, "verdicts": [
        _v(1, "signal", "SENIAL_UNO"), _v(2, "signal", "SENIAL_DOS"),
        _v(3, "noise", "RUIDO_UNO"), _v(4, "noise", "RUIDO_DOS"),
        _v(5, "noise", "RUIDO_TRES"),
    ]}
    block = build_tickets_context_block(mining)
    contenido = block["content"]

    assert "SENIAL_UNO" in contenido and "SENIAL_DOS" in contenido      # PRESENCIA
    for ruido in ("RUIDO_UNO", "RUIDO_DOS", "RUIDO_TRES"):
        assert ruido not in contenido                                    # AUSENCIA

    # Sin ningun signal, no hay bloque (no se ensucia el prompt con nada).
    assert build_tickets_context_block({"total": 1, "noise": 1,
                                        "verdicts": [_v(9, "noise", "X")]}) is None


# ===========================================================================
# Plan 284 F5.0 - habilitar lo que F5 da por sentado
# ===========================================================================

def test_plan284_invoke_documenter_acepta_override(monkeypatch):
    """El override es un PARAMETRO real, no un literal hardcodeado."""
    import agent_runner
    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, invoke_documenter

    capturado = {}

    def _fake_run_agent(**kw):
        capturado.update(kw)
        return 4242

    monkeypatch.setattr(agent_runner, "run_agent", _fake_run_agent)
    monkeypatch.setattr(doc_documenter, "_ensure_documenter_ticket", lambda p: 1)
    monkeypatch.setattr(doc_documenter, "_wait_and_read_output", lambda e: "")

    # PRESENCIA: lo que le paso es lo que llega a run_agent.
    invoke_documenter(DocumenterMode.ENRIQUECER, [], "P", "claude_code_cli",
                      system_prompt_override="PROMPT_X")
    assert capturado["system_prompt_override"] == "PROMPT_X"

    # AUSENCIA GEMELA (backward-compat exacta): sin el kwarg vuelve el default.
    capturado.clear()
    invoke_documenter(DocumenterMode.ENRIQUECER, [], "P", "claude_code_cli")
    assert capturado["system_prompt_override"] == doc_documenter._DEFAULT_DOCUMENTADOR_PROMPT


def test_plan284_invoke_raw_stage_devuelve_texto(monkeypatch):
    """Devuelve texto crudo y NO pasa por parse_proposals."""
    import agent_runner
    from services import doc_documenter
    from services.doc_documenter import invoke_raw_stage

    monkeypatch.setattr(agent_runner, "run_agent", lambda **kw: 77)
    monkeypatch.setattr(doc_documenter, "_ensure_documenter_ticket", lambda p: 1)
    monkeypatch.setattr(doc_documenter, "_wait_and_read_output",
                        lambda e: "TEXTO_CRUDO_DE_LA_ETAPA")

    def _boom(raw):
        raise AssertionError("invoke_raw_stage NO debe parsear: es prosa, no bloques DOC")

    monkeypatch.setattr(doc_documenter, "parse_proposals", _boom)

    out = invoke_raw_stage("PROMPT_ETAPA", [], "P", "claude_code_cli")
    assert out == "TEXTO_CRUDO_DE_LA_ETAPA"


def test_plan284_invoke_raw_stage_degrada_sin_lanzar(monkeypatch):
    """Ante error devuelve "" y nunca propaga la excepcion."""
    import agent_runner
    from services import doc_documenter
    from services.doc_documenter import invoke_raw_stage

    def _explota(**kw):
        raise RuntimeError("runtime caido")

    monkeypatch.setattr(agent_runner, "run_agent", _explota)
    monkeypatch.setattr(doc_documenter, "_ensure_documenter_ticket", lambda p: 1)
    assert invoke_raw_stage("P", [], "P", "claude_code_cli") == ""


# ===========================================================================
# Plan 284 F5 - pipeline de 5 etapas con veredicto + A1 presupuesto
# ===========================================================================

def test_plan284_stage_order_es_el_contrato():
    from services.doc_documenter import STAGE_ORDER

    assert len(STAGE_ORDER) == 5
    assert [s.value for s in STAGE_ORDER] == [
        "PROPONER", "CRITICAR", "MEJORAR", "IMPLEMENTAR", "VERIFICAR"]


def test_plan284_verdict_tabla():
    from services.doc_documenter import (VERDICT_COMPLETA, VERDICT_INSUFICIENTE,
                                         VERDICT_PARCIAL, compute_verify_verdict)

    # Regla 1: sin archivos escritos, INSUFICIENTE sin importar el ratio.
    assert compute_verify_verdict(0, 0, 1.0) == VERDICT_INSUFICIENTE
    # Regla 2: mas rechazados que escritos.
    assert compute_verify_verdict(2, 3, 1.0) == VERDICT_INSUFICIENTE
    # Regla 3 + frontera exacta 0.8.
    assert compute_verify_verdict(5, 0, 0.8) == VERDICT_COMPLETA
    assert compute_verify_verdict(5, 0, 1.0) == VERDICT_COMPLETA
    # 0.79 cae a PARCIAL (frontera del otro lado).
    assert compute_verify_verdict(5, 0, 0.79) == VERDICT_PARCIAL
    # Regla 4: con rechazos, PARCIAL.
    assert compute_verify_verdict(5, 1, 1.0) == VERDICT_PARCIAL
    # Nunca lanza.
    assert compute_verify_verdict(None, None, None) == VERDICT_INSUFICIENTE


def test_plan284_stage_artifact_is_usable_tabla():
    from services.doc_documenter import stage_artifact_is_usable as u

    ctx = [{"content": "el modulo services/doc_graph.py hace el grafo"}]
    assert u("", ctx) is False
    assert u("x" * 199, ctx) is False
    # 250 chars SIN ninguna ruta del contexto: es prosa, no un plan.
    # Este es el caso que la v1 dejaba pasar y disparaba 2 invocaciones al pedo.
    assert u("bla " * 80, ctx) is False
    # 250 chars que SI mencionan una ruta real del contexto.
    bueno = "Voy a documentar services/doc_graph.py. " + ("detalle " * 40)
    assert len(bueno) >= 200 and u(bueno, ctx) is True
    # Nunca lanza.
    assert u(None, None) is False


def test_plan284_budget_exhausted_tabla():
    from services.doc_documenter import budget_exhausted as b

    assert b(0, 12) is False
    assert b(11, 12) is False
    assert b(12, 12) is True          # frontera
    # EL CASO QUE IMPORTA: cero NO es infinito.
    assert b(3, 0) is True
    assert b(3, -1) is True
    # Nunca lanza.
    assert b("x", 12) is False


def _stub_para_run(monkeypatch, tmp_path):
    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, DocumenterPlan
    monkeypatch.setattr(doc_documenter, "plan_documenter_run",
                        lambda *a, **k: DocumenterPlan(
                            status="SANA", modes=[DocumenterMode.ENRIQUECER],
                            notes_to_normalize=[], notes_to_update=[], reason="t"))
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "sg", "kind": "sg", "title": "SG", "content": "x"})
    monkeypatch.setattr(doc_documenter, "prepare_doc_branch",
                        lambda *a, **k: (str(tmp_path), None, "rama", False))
    monkeypatch.setattr(doc_documenter, "_health_for_root",
                        lambda *a, **k: {"status": "SANA", "reasons": [],
                                         "frontmatter_ratio": 0.0,
                                         "wikilink_edges": 0, "uncovered_modules": []})
    monkeypatch.setattr(doc_documenter, "_persist_run_report", lambda *a, **k: None)
    monkeypatch.setattr(doc_documenter, "list_runs", lambda *a, **k: [])


def test_plan284_sin_autoaplicado_el_run_espera_aprobacion(monkeypatch, tmp_path,
                                                           clean_run_registry):
    """[RIEL HUMAN-IN-THE-LOOP] El run se detiene ANTES de escribir."""
    from config import config
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_AUTOAPPLY", False)
    monkeypatch.setattr(doc_documenter, "invoke_raw_stage",
                        lambda *a, **k: "PLAN: documentar services/doc_graph.py. " + "d" * 300)

    escrituras = []
    monkeypatch.setattr(doc_documenter, "apply_proposals",
                        lambda *a, **k: escrituras.append(1))
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    _stub_para_run(monkeypatch, tmp_path)

    report = doc_documenter.run_documenter("P", "claude_code_cli")

    # PRESENCIA: el run quedo esperando al operador y con veredicto explicito.
    assert report["state"] == "awaiting_approval"
    assert report["verdict"] == doc_documenter.VERDICT_PENDIENTE
    # AUSENCIA: no se escribio NI UN archivo.
    assert report["written"] == []
    assert escrituras == [], "apply_proposals no debe llamarse antes de aprobar"


def test_plan284_corte_de_costo_sin_plan(monkeypatch, tmp_path, clean_run_registry):
    """Si PROPONER vuelve vacio, CRITICAR y MEJORAR se saltean: 1 sola llamada."""
    from config import config
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
    # PRECONDICION OBLIGATORIA: con AUTOAPPLY True el run seguiria a IMPLEMENTAR
    # y el contador subiria por los modos del 113 => el "exactamente 1" seria
    # un falso rojo.
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_AUTOAPPLY", False)

    llamadas = []

    def _raw(*a, **k):
        llamadas.append(1)
        return ""

    monkeypatch.setattr(doc_documenter, "invoke_raw_stage", _raw)
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    _stub_para_run(monkeypatch, tmp_path)

    report = doc_documenter.run_documenter("P", "claude_code_cli")

    assert len(llamadas) == 1, f"se gastaron {len(llamadas)} invocaciones en vez de 1"
    estados = {s["stage"]: s["state"] for s in report["stages"]}
    assert estados["CRITICAR"] == "skipped"
    assert estados["MEJORAR"] == "skipped"


def test_plan284_run_respeta_el_presupuesto(monkeypatch, tmp_path, clean_run_registry):
    """Con presupuesto 2, se invoca EXACTAMENTE 2 veces: no se excede en uno."""
    from config import config
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_AUTOAPPLY", True)
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_MAX_LLM_CALLS", 2)

    llamadas = []

    def _raw(*a, **k):
        llamadas.append(1)
        return "PLAN: documentar services/doc_graph.py. " + "d" * 300

    monkeypatch.setattr(doc_documenter, "invoke_raw_stage", _raw)
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    # El corte de costo exige que el artefacto mencione una ruta PRESENTE en el
    # contexto. El bloque canónico real no trae ninguna ruta de archivo, así que
    # sin esto CRITICAR se saltearía por "sin plan que criticar" y el tope
    # nunca se ejercitaría (el test mediría otra cosa).
    monkeypatch.setattr(doc_documenter, "_sistema_readonly_block",
                        lambda p: {"id": "sis", "kind": "canonical-index",
                                   "title": "canonico",
                                   "content": "el modulo services/doc_graph.py arma el grafo"})
    _stub_para_run(monkeypatch, tmp_path)

    report = doc_documenter.run_documenter("P", "claude_code_cli")

    assert len(llamadas) == 2, f"el tope no se respeto: {len(llamadas)}"
    assert report["state"] == "budget_exhausted"
    assert report["llm_calls_budget"] == 2


def test_plan284_pipeline_off_es_backward_compatible(monkeypatch, tmp_path,
                                                     clean_run_registry):
    """Con las etapas OFF el reporte NO trae stages ni verdict."""
    from config import config
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    _stub_para_run(monkeypatch, tmp_path)

    report = doc_documenter.run_documenter("P", "claude_code_cli")

    assert "stages" not in report          # AUSENCIA
    assert "verdict" not in report
    # PRESENCIA de control: el reporte sigue teniendo las claves de siempre.
    for clave in ("state", "written", "skipped", "health_before", "health_after",
                  "branch", "degraded", "diff_stat", "modes_skipped", "files"):
        assert clave in report, f"falta la clave historica {clave}"


# ===========================================================================
# Plan 285 F0 — red-team del pipeline: el contexto que NO cruza la barrera
# ===========================================================================

import contextlib  # noqa: E402


class _NoopSessionPlan285:
    """Sesion inerte: ningun test del 285 puede tocar backend/data/stacky_agents.db.
    El corpus vivo tiene 51 chunks basura JUSTAMENTE por un pytest suelto."""

    def __init__(self, sink):
        self._sink = sink

    def query(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def delete(self, *a, **k):
        return 0

    def add(self, obj):
        self._sink.append(obj)

    def all(self):
        return []

    def order_by(self, *a, **k):
        return self

    def count(self):
        return 0

    def limit(self, *a, **k):
        return self


@contextlib.contextmanager
def _scope_aislado(sink):
    yield _NoopSessionPlan285(sink)


def _corpus_temporal(monkeypatch, tmp_path):
    """Arma un workspace con 3 docs de proyecto y 2 planes, y aisla la DB.

    Devuelve (workspace_root, sink) donde sink acumula los DocChunk que se
    habrian persistido.
    """
    from config import config
    from services import docs_rag

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", True)
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "arquitectura.md").write_text(
        "# Arquitectura\n\n## Modulos\n\nCENTINELA_CORPUS_285 describe los modulos.\n",
        encoding="utf-8")
    (docs / "flujo.md").write_text(
        "# Flujo\n\n## Datos\n\nEl flujo de datos entre integraciones.\n", encoding="utf-8")
    (docs / "decisiones.md").write_text(
        "# Decisiones\n\n## Tecnicas\n\nDecisiones tecnicas del proyecto.\n", encoding="utf-8")
    (docs / "101_PLAN_X.md").write_text("# Plan X\n\nUn plan, no es doc.\n", encoding="utf-8")
    (docs / "102_PLAN_Y.md").write_text("# Plan Y\n\nOtro plan.\n", encoding="utf-8")

    sink: list = []
    monkeypatch.setattr(docs_rag, "session_scope", lambda: _scope_aislado(sink))
    return str(tmp_path), sink


def test_f0_corpus_rag_del_proyecto_activo_no_esta_vacio(monkeypatch, tmp_path):
    """K1: hoy docs_index tiene 51 chunks y CERO documentos reales.
    ensure_corpus_indexed no existe: ImportError/AttributeError."""
    from config import config
    from services import doc_documenter, doc_taxonomy

    ws, sink = _corpus_temporal(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED", True, raising=False)

    out = doc_documenter.ensure_corpus_indexed("P285", ws)

    assert out["enabled"] is True, f"la flag no llego al hook: {out}"
    assert out["chunks_indexed"] >= 3, f"el corpus quedo vacio: {out}"
    assert out["skipped_plans"] == 2, f"el filtro de planes no reporto: {out}"

    rutas = [getattr(c, "file_path", "") for c in sink]
    unidas = " | ".join(rutas)
    # PRESENCIA: los 3 docs reales del proyecto SI estan.
    for esperado in ("arquitectura.md", "flujo.md", "decisiones.md"):
        assert esperado in unidas, f"falto {esperado}: {unidas}"
    # AUSENCIA (con su gemelo de presencia ya asertado arriba): ningun plan entro.
    for r in rutas:
        assert not doc_taxonomy.is_plan_doc(r.split("docs/")[-1]), \
            f"un documento de plan contamino el corpus: {r}"


def test_f0_el_corpus_llega_al_prompt(monkeypatch, tmp_path):
    """C1: `grep -rn docs_rag doc_documenter.py` daba 0 lineas.
    El corpus se indexaba y NADIE lo leia desde el Documentador."""
    from config import config
    from services import doc_documenter, docs_rag

    monkeypatch.setattr(config, "STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED", True, raising=False)

    class _Hit:
        def __init__(self, fp, sh, txt):
            self.file_path, self.section_heading, self.chunk_text = fp, sh, txt
            self.score = 1.0

    monkeypatch.setattr(docs_rag, "search_hybrid",
                        lambda *a, **k: [_Hit("docs/arquitectura.md", "## Modulos",
                                              "CENTINELA_CORPUS_285 describe los modulos.")])

    bloque = doc_documenter._corpus_block("P285")

    assert bloque is not None, "el retrieval no produjo bloque"
    assert bloque["id"] == "docs-corpus"
    assert "docs/arquitectura.md" in bloque["content"]
    # El renderizador CLI ignora `kind`: la senal tiene que estar en title+content.
    assert bloque["title"].strip() != ""


def test_f0_las_etapas_de_papel_reciben_el_contexto_rico(monkeypatch, tmp_path,
                                                         clean_run_registry):
    """C2: con los defaults (STAGES on, AUTOAPPLY off) run_documenter retorna en
    :1335 y las 3 llamadas al LLM que el operador LEE reciben UN solo bloque
    (:1287). Todo el contexto rico del 284 vive del otro lado de la barrera HITL."""
    from config import config
    from services import doc_documenter

    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_AUTOAPPLY", False)
    monkeypatch.setattr(config, "STACKY_DOCS_CORPUS_RETRIEVAL_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_DOCS_CORPUS_AUTOINDEX_ENABLED", False, raising=False)

    capturados: list[list[dict]] = []

    def _raw(prompt, blocks, project, runtime, **k):
        capturados.append(list(blocks or []))
        return "PLAN: documentar services/doc_graph.py. " + "d" * 300

    monkeypatch.setattr(doc_documenter, "invoke_raw_stage", _raw)
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    monkeypatch.setattr(doc_documenter, "_corpus_block",
                        lambda p: {"id": "docs-corpus", "kind": "docs-corpus",
                                   "title": "DOC YA ESCRITA", "content": "x"},
                        raising=False)
    monkeypatch.setattr(doc_documenter, "_tickets_block_safe",
                        lambda p: {"id": "tickets-signal", "kind": "t",
                                   "title": "TICKETS", "content": "y"},
                        raising=False)
    _stub_para_run(monkeypatch, tmp_path)
    # DESPUES de _stub_para_run: ese helper compartido pisa _subgraph_block con
    # un bloque de id "sg". Este test asserta el id REAL del contrato, asi que
    # lo restituye — relajar el assert a "sg" seria aflojar el gate.
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "doc-subgraph", "kind": "doc-subgraph",
                                   "title": "Subgrafo documental", "content": "x"})

    doc_documenter.run_documenter("P", "claude_code_cli")

    assert capturados, "no se ejecuto ninguna etapa de papel"
    primera = capturados[0]
    ids = [b.get("id") for b in primera]
    assert len(primera) >= 4, f"la etapa PROPONER recibio {len(primera)} bloques: {ids}"
    assert "docs-corpus" in ids, f"falta el corpus en la etapa de papel: {ids}"
    assert "doc-subgraph" in ids, f"falta el subgrafo en la etapa de papel: {ids}"


def test_f0_ticket_mining_queda_en_el_run_record(monkeypatch, tmp_path,
                                                 clean_run_registry):
    """K4: api/docs.py:363 expone `ticket_mining` y NADIE de produccion la
    escribe => devuelve {} siempre.

    autoapply_override=True es OBLIGATORIO: con los defaults run_documenter
    retorna en :1335 sin llegar nunca al loop de modos (C11)."""
    from config import config
    from services import doc_documenter, doc_ticket_mining
    from services.doc_ticket_mining import TicketVerdict

    monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)
    monkeypatch.setattr(config, "STACKY_DOCS_TICKET_TRIAGE_VISIBLE_ENABLED", True,
                        raising=False)

    ruidosos = [TicketVerdict(ticket_id=i, external_id=-i, tracker_type="demo",
                              title=f"test {i}", verdict="noise",
                              reasons=["sin_descripcion", "titulo_ruido"], score=-4)
                for i in range(1, 6)]
    bueno = TicketVerdict(ticket_id=99, external_id=99, tracker_type="gitlab",
                          title="Refactor del motor de cobranzas", verdict="signal",
                          reasons=["descripcion_extensa:900"], score=3)
    monkeypatch.setattr(doc_ticket_mining, "mine_project_tickets",
                        lambda *a, **k: {"enabled": True, "scope": "project",
                                         "total": 6, "signal": 1, "noise": 5,
                                         "by_tracker": {"demo": 5, "gitlab": 1},
                                         "verdicts": ruidosos + [bueno],
                                         "truncated": False})

    guardado: dict = {}
    monkeypatch.setattr(doc_documenter, "_persist_run_report",
                        lambda pid, rep: guardado.update(rep))
    monkeypatch.setattr(doc_documenter, "invoke_documenter", lambda *a, **k: [])
    _stub_para_run(monkeypatch, tmp_path)
    monkeypatch.setattr(doc_documenter, "_persist_run_report",
                        lambda pid, rep: guardado.update(rep))
    from services.doc_documenter import DocumenterMode, DocumenterPlan
    monkeypatch.setattr(doc_documenter, "plan_documenter_run",
                        lambda *a, **k: DocumenterPlan(
                            status="SANA", modes=[DocumenterMode.RECONSTRUIR],
                            notes_to_normalize=[], notes_to_update=[], reason="t"))

    doc_documenter.run_documenter("P", "claude_code_cli", autoapply_override=True)

    tm = guardado.get("ticket_mining") or {}
    assert "reason_counts" in tm, f"la clave sigue muerta: {sorted(tm)}"
    assert tm.get("noise_sample"), "no hay muestra de descartados"
    for fila in tm["noise_sample"]:
        assert fila.get("reasons"), f"un descartado sin motivo: {fila}"


def test_f0_truncamiento_se_declara_en_el_prompt():
    """El bloque afirma 'Se barrieron N tickets' con N YA RECORTADO por el cap
    SQL (doc_ticket_mining.py:201). El modelo cree que vio todo."""
    from services.doc_ticket_mining import TicketVerdict, build_tickets_context_block

    signal = [TicketVerdict(ticket_id=1, external_id=1, tracker_type="gitlab",
                            title="Historia documentable del modulo", verdict="signal",
                            reasons=["descripcion_extensa:900"], score=3)]

    truncado = build_tickets_context_block(
        {"total": 500, "total_rows": 900, "truncated": True,
         "signal": 1, "noise": 499, "verdicts": signal})
    assert "TRUNCADO" in truncado["content"], \
        f"el truncamiento SQL no se declara: {truncado['content'][:200]}"

    # GEMELO: sin truncamiento de ningun eje, el bloque afirma COMPLETO.
    completo = build_tickets_context_block(
        {"total": 6, "total_rows": 6, "truncated": False,
         "signal": 1, "noise": 5, "verdicts": signal})
    assert "COMPLETO" in completo["content"], \
        f"el barrido completo no se declara: {completo['content'][:200]}"
    assert "TRUNCADO" not in completo["content"]


def test_f0_subgrafo_llega_a_reconstruir_y_completar(monkeypatch):
    """K5: el subgrafo se inyecta SOLO en ENRIQUECER (doc_documenter.py:339),
    de CINCO modos (:56-61)."""
    from services import doc_documenter
    from services.doc_documenter import (DocumenterMode, DocumenterPlan,
                                         build_context_for_mode)

    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "doc-subgraph", "kind": "sg",
                                   "title": "SG", "content": "x"})
    monkeypatch.setattr(doc_documenter, "_read_note_content", lambda *a, **k: "cuerpo")
    plan = DocumenterPlan(status="SANA", modes=[], notes_to_normalize=["a.md"],
                          notes_to_update=["b.md"])

    def _ids(mode):
        return [b.get("id") for b in build_context_for_mode(mode, plan, "P")]

    # PRESENCIA en los tres que documentan de cero o enriquecen.
    for mode in (DocumenterMode.RECONSTRUIR, DocumenterMode.COMPLETAR,
                 DocumenterMode.ENRIQUECER):
        assert "doc-subgraph" in _ids(mode), f"{mode.value} no ve el grafo"
    # AUSENCIA GEMELA en los dos que no lo necesitan.
    for mode in (DocumenterMode.NORMALIZAR, DocumenterMode.ACTUALIZAR):
        assert "doc-subgraph" not in _ids(mode), f"{mode.value} no deberia verlo"


def test_f0_fallo_del_barrido_no_es_mudo(monkeypatch):
    """El except de doc_documenter.py:336 traga con logger.warning: el modelo
    documenta sin historia y nadie se entera."""
    from services import doc_documenter, doc_ticket_mining
    from services.doc_documenter import (DocumenterMode, DocumenterPlan,
                                         build_context_for_mode)

    def _boom(*a, **k):
        raise RuntimeError("la base no responde")

    monkeypatch.setattr(doc_ticket_mining, "mine_project_tickets", _boom)
    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "doc-subgraph", "kind": "sg",
                                   "title": "SG", "content": "x"})
    plan = DocumenterPlan(status="SANA", modes=[], notes_to_normalize=[],
                          notes_to_update=[])

    blocks = build_context_for_mode(DocumenterMode.RECONSTRUIR, plan, "P")
    titulos = " | ".join(str(b.get("title", "")) for b in blocks)

    assert "NO disponible" in titulos, \
        f"el fallo del barrido quedo mudo para el modelo: {titulos}"
    # PRESENCIA de control: el resto del contexto sigue armandose.
    assert any(b.get("id") == "sistema-readonly" for b in blocks)


# ===========================================================================
# Plan 285 F3 — el descarte de tickets se vuelve trazable
# ===========================================================================

def _verdicts_285(n_noise: int = 10, n_signal: int = 2):
    from services.doc_ticket_mining import TicketVerdict
    ruido = [TicketVerdict(ticket_id=i, external_id=-i, tracker_type="demo",
                           title=f"test {i}", verdict="noise",
                           reasons=["sin_descripcion", "ticket_interno_de_stacky"],
                           score=-5 - i)
             for i in range(1, n_noise + 1)]
    senal = [TicketVerdict(ticket_id=900 + i, external_id=900 + i,
                           tracker_type="gitlab",
                           title=f"Historia documentable del modulo {i}",
                           verdict="signal",
                           reasons=[f"descripcion_extensa:{900 + i}"], score=3)
             for i in range(n_signal)]
    return ruido + senal


def test_f3_reason_counts_suma_todo_el_barrido():
    """El histograma cuenta sobre TODO el barrido, no sobre la muestra: si
    contara sobre la muestra el operador leeria un histograma sesgado."""
    from services.doc_ticket_mining import build_triage_report

    verdicts = _verdicts_285(n_noise=10, n_signal=2)
    out = build_triage_report(
        {"total": 12, "total_rows": 12, "truncated": False, "signal": 2,
         "noise": 10, "by_tracker": {"demo": 10, "gitlab": 2},
         "verdicts": verdicts},
        max_noise=3)

    assert len(out["noise_sample"]) == 3, "la muestra no respeto max_noise"
    assert sum(out["reason_counts"].values()) >= 10, \
        f"el histograma se calculo sobre la muestra: {out['reason_counts']}"
    # PRESENCIA de una key concreta, nunca `!= {}`.
    assert out["reason_counts"]["sin_descripcion"] == 10
    # Los PEORES primero: score ascendente.
    scores = [f["score"] for f in out["noise_sample"]]
    assert scores == sorted(scores), f"la muestra no prioriza los peores: {scores}"
    # Nunca lanza.
    assert build_triage_report(None)["reason_counts"] == {}


def test_f3_build_context_for_mode_conserva_su_firma(monkeypatch):
    """R4 — prohibido cambiar su firma: la hermana es la que devuelve el triage."""
    from services import doc_documenter
    from services.doc_documenter import (DocumenterMode, DocumenterPlan,
                                         build_context_for_mode)

    monkeypatch.setattr(doc_documenter, "_subgraph_block",
                        lambda p: {"id": "doc-subgraph", "kind": "sg",
                                   "title": "SG", "content": "x"})
    plan = DocumenterPlan(status="SANA", modes=[], notes_to_normalize=[],
                          notes_to_update=[])

    tres = build_context_for_mode(DocumenterMode.ENRIQUECER, plan, "P")
    cuatro = build_context_for_mode(DocumenterMode.ENRIQUECER, plan, "P", "nota")
    assert isinstance(tres, list) and isinstance(cuatro, list)
    assert all(isinstance(b, dict) for b in tres)
    # PRESENCIA: sigue devolviendo el contexto real, no una lista vacia.
    assert any(b.get("id") == "sistema-readonly" for b in tres)


def test_f3_truncamiento_por_caracteres_tambien_se_declara():
    """C9 — hay DOS ejes de truncamiento. Declarar COMPLETO con el segundo
    activo cambia una afirmacion falsa por otra mas enfatica."""
    from services.doc_ticket_mining import build_tickets_context_block

    verdicts = _verdicts_285(n_noise=0, n_signal=40)
    mining = {"total": 40, "total_rows": 40, "truncated": False,
              "signal": 40, "noise": 0, "verdicts": verdicts}

    corto = build_tickets_context_block(mining, max_chars=120)
    assert "TRUNCADO" in corto["content"], \
        f"el corte por caracteres no se declara: {corto['content'][:250]}"

    # GEMELO: con espacio de sobra, el bloque afirma COMPLETO.
    largo = build_tickets_context_block(mining, max_chars=100000)
    assert "COMPLETO" in largo["content"]
    assert "TRUNCADO" not in largo["content"]


# ===========================================================================
# Plan 285 F1.1 / F1.3 — skipped_plans, huerfanos, backup y purga
#
# NINGUNO de estos tests puede tocar backend/data/stacky_agents.db: los 51
# chunks basura que motivaron este plan nacieron de un pytest suelto. Todos
# usan una base SQLite propia en tmp_path.
# ===========================================================================

@pytest.fixture
def corpus_db(tmp_path, monkeypatch):
    """Base SQLite REAL pero temporal, sólo con la tabla docs_index."""
    import contextlib

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from services import docs_rag

    engine = create_engine(f"sqlite:///{tmp_path / 'corpus.db'}")
    docs_rag.DocChunk.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine)

    @contextlib.contextmanager
    def _scope():
        s = Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    monkeypatch.setattr(docs_rag, "session_scope", _scope)
    return _scope


def _sembrar(scope, filas):
    from services.docs_rag import DocChunk
    with scope() as s:
        for proyecto, ruta in filas:
            s.add(DocChunk(project_name=proyecto, file_path=ruta,
                           section_heading="## X", chunk_text="cuerpo",
                           term_freqs_json="{}", doc_norm=1.0))


def test_f1_index_project_reporta_skipped_plans(monkeypatch, tmp_path, corpus_db):
    from config import config
    from services import docs_rag

    monkeypatch.setattr(config, "STACKY_DOCS_TAXONOMY_ENABLED", True)
    docs = tmp_path / "ws" / "docs"
    docs.mkdir(parents=True)
    for n in ("guia.md", "arquitectura.md", "flujo.md"):
        (docs / n).write_text(f"# {n}\n\nContenido real.\n", encoding="utf-8")
    for n in ("101_PLAN_X.md", "102_PLAN_Y.md"):
        (docs / n).write_text(f"# {n}\n\nUn plan.\n", encoding="utf-8")

    res = docs_rag.index_project("PTMP", str(tmp_path / "ws"), "docs")

    assert res["skipped_plans"] == 2, f"el filtro no reporto: {res}"
    assert res["files_scanned"] == 3, f"debia escanear 3: {res}"
    assert res["chunks_indexed"] >= 3


def test_f1_purga_nunca_borra_un_proyecto_configurado(monkeypatch, corpus_db):
    """Guarda (a): el operador puede equivocarse; el codigo no lo obedece."""
    from services import docs_rag

    _sembrar(corpus_db, [("REAL", "a.md"), ("REAL", "b.md"), ("C1", "n0.md")])
    monkeypatch.setattr(docs_rag, "_proyectos_configurados", lambda: {"REAL"})

    out = docs_rag.purge_orphan_corpus_projects(["REAL", "C1"], expected_rows=1)

    assert out["ok"] is True, out
    assert out["skipped_configured"] == ["REAL"]
    with corpus_db() as s:
        # AUSENCIA: el huerfano se fue.
        assert s.query(docs_rag.DocChunk).filter_by(project_name="C1").count() == 0
        # GEMELO DE PRESENCIA en la MISMA llamada: el configurado sigue entero.
        assert s.query(docs_rag.DocChunk).filter_by(project_name="REAL").count() == 2


def test_f1_purga_aborta_si_el_conteo_no_coincide(monkeypatch, corpus_db):
    """Guarda (b): entre que el operador miro la lista y confirmo, algo cambio."""
    from services import docs_rag

    _sembrar(corpus_db, [("C1", "n0.md"), ("C1", "n1.md"), ("C1", "n2.md")])
    monkeypatch.setattr(docs_rag, "_proyectos_configurados", lambda: {"REAL"})

    out = docs_rag.purge_orphan_corpus_projects(["C1"], expected_rows=2)

    assert out["ok"] is False and out["reason"] == "row_count_mismatch"
    assert out["deleted"] == 0
    with corpus_db() as s:
        assert s.query(docs_rag.DocChunk).count() == 3, "borro pese al mismatch"
    # GEMELO: con el conteo correcto SI borra (prueba que el guard discrimina,
    # no que la funcion este rota).
    ok = docs_rag.purge_orphan_corpus_projects(["C1"], expected_rows=3)
    assert ok["ok"] is True and ok["deleted"] == 3


def test_f1_purga_deja_backup_leible(monkeypatch, tmp_path, corpus_db):
    """Guarda (c): docs_index es derivada, pero de proyectos que ya NO existen.
    Nadie la puede regenerar: el backup es lo unico que hace reversible esto."""
    import json as _json

    from services import docs_rag

    _sembrar(corpus_db, [("C1", "n0.md"), ("C1", "n1.md")])
    monkeypatch.setattr(docs_rag, "_proyectos_configurados", lambda: {"REAL"})
    destino = tmp_path / "backups"

    out = docs_rag.purge_orphan_corpus_projects(
        ["C1"], expected_rows=2, backup_dir=str(destino))

    assert out["ok"] is True and out["backup_path"]
    ruta = pathlib.Path(out["backup_path"])
    assert ruta.exists(), "no quedo backup"
    lineas = [l for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lineas) == 2, f"el backup no tiene tantas lineas como filas: {len(lineas)}"
    fila = _json.loads(lineas[0])
    for clave in ("project_name", "file_path", "chunk_text"):
        assert clave in fila, f"el backup perdio {clave}"


def test_f1_orphans_solo_lista_los_no_configurados(monkeypatch, corpus_db):
    from services import docs_rag

    _sembrar(corpus_db, [("REAL", "a.md"), ("C1", "n0.md"), ("C1", "n1.md"),
                         ("D1", "b.md")])
    monkeypatch.setattr(docs_rag, "_proyectos_configurados", lambda: {"REAL"})

    out = docs_rag.list_orphan_corpus_projects()
    nombres = [o["project_name"] for o in out]

    # PRESENCIA de los dos huerfanos, con su conteo.
    assert nombres == ["C1", "D1"], f"orden por chunks descendente: {out}"
    assert out[0]["chunks"] == 2 and out[0]["files"] == 2
    # AUSENCIA GEMELA: el configurado NO aparece.
    assert "REAL" not in nombres
    # Sin lista de proyectos no se declara huerfano a NADIE (si no, el fallo de
    # una lectura de configuracion convierte todo el corpus en basura borrable).
    monkeypatch.setattr(docs_rag, "_proyectos_configurados", lambda: set())
    assert docs_rag.list_orphan_corpus_projects() == []
