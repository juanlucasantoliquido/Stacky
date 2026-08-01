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
    """Con la flag OFF: las 8 claves presentes, enabled=False y ceros."""
    from config import config
    from services.doc_ticket_mining import mine_project_tickets

    monkeypatch.setattr(config, "STACKY_DOCS_TICKET_MINING_ENABLED", False)
    out = mine_project_tickets("P")

    esperadas = {"enabled", "scope", "total", "signal", "noise",
                 "by_tracker", "verdicts", "truncated"}
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
