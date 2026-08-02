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


# ===========================================================================
# Plan 284 F6 - radiografia: cobertura sobre el grafo existente + delta (A2)
# ===========================================================================

def _grafo(uncovered, modulos=3, notas=2, orphans=None):
    nodes = [{"kind": "code", "path": f"mod{i}.py"} for i in range(modulos)]
    nodes += [{"kind": "note", "path": f"docs/n{i}.md"} for i in range(notas)]
    return {"nodes": nodes, "orphans": orphans or [],
            "doc_health": {"uncovered_modules": list(uncovered)}}


def test_plan284_compute_coverage_forma_garantizada(monkeypatch):
    from config import config
    from services.doc_radiography import compute_coverage

    monkeypatch.setattr(config, "STACKY_DOCS_RADIOGRAPHY_ENABLED", True)
    out = compute_coverage(_grafo([]), None)

    esperadas = {"enabled", "modules_total", "modules_covered", "coverage_ratio",
                 "uncovered", "orphan_notes", "by_doc_class"}
    assert set(out.keys()) == esperadas
    assert out["enabled"] is True

    # Con la flag OFF: la MISMA forma, con enabled=False.
    monkeypatch.setattr(config, "STACKY_DOCS_RADIOGRAPHY_ENABLED", False)
    off = compute_coverage(_grafo([]), None)
    assert set(off.keys()) == esperadas
    assert off["enabled"] is False


def test_plan284_coverage_ratio_fronteras(monkeypatch):
    from config import config
    from services.doc_radiography import compute_coverage

    monkeypatch.setattr(config, "STACKY_DOCS_RADIOGRAPHY_ENABLED", True)

    # Sin modulos: ratio 1.0. NOTA DE HONESTIDAD (hallazgo del juez): si la
    # salud viene SANA/SIN_DOCS, uncovered llega [] y el ratio da 1.0 aunque no
    # haya ni una nota. El veredicto lo compensa: con written==0 el run es
    # INSUFICIENTE sin importar el ratio.
    vacio = {"nodes": [], "orphans": [], "doc_health": {"uncovered_modules": []}}
    assert compute_coverage(vacio, None)["coverage_ratio"] == 1.0

    # 4 de 5 cubiertos -> 0.8
    g = _grafo(["mod4.py"], modulos=5)
    r = compute_coverage(g, None)
    assert (r["modules_total"], r["modules_covered"], r["coverage_ratio"]) == (5, 4, 0.8)

    # 0 de 5 -> 0.0
    g0 = _grafo([f"mod{i}.py" for i in range(5)], modulos=5)
    r0 = compute_coverage(g0, None)
    assert r0["coverage_ratio"] == 0.0


def test_plan284_coverage_no_recalcula_health(monkeypatch):
    """Lee graph["doc_health"]: NO reconstruye el grafo ni recalcula la salud."""
    from config import config
    from services import doc_graph
    from services.doc_radiography import compute_coverage

    monkeypatch.setattr(config, "STACKY_DOCS_RADIOGRAPHY_ENABLED", True)

    def _boom(*a, **k):
        raise AssertionError("compute_coverage NO debe recalcular la salud")

    monkeypatch.setattr(doc_graph, "classify_doc_health", _boom)
    monkeypatch.setattr(doc_graph, "build_graph", _boom)

    out = compute_coverage(_grafo(["mod2.py"]), None)
    # PRESENCIA: devuelve la forma completa igual.
    assert out["enabled"] is True and out["modules_total"] == 3
    assert out["uncovered"] == ["mod2.py"]


def test_plan284_coverage_delta_tabla():
    from services.doc_radiography import compute_coverage_delta

    claves = {"has_previous", "ratio_delta", "modules_closed", "modules_opened"}

    # Sin run previo: las 4 claves presentes, has_previous False.
    sin = compute_coverage_delta({"coverage_ratio": 0.5, "uncovered": ["a"]}, None)
    assert set(sin.keys()) == claves
    assert sin["has_previous"] is False

    previo = {"enabled": True, "coverage_ratio": 0.4,
              "uncovered": ["a", "b", "c", "d", "e"]}
    actual = {"enabled": True, "coverage_ratio": 0.8, "uncovered": ["a", "b"]}
    d = compute_coverage_delta(actual, previo)
    assert d["has_previous"] is True
    assert round(d["ratio_delta"], 4) == 0.4
    assert d["modules_closed"] == ["c", "d", "e"]   # PRESENCIA
    assert d["modules_opened"] == []                # AUSENCIA GEMELA

    # Regresion inversa: lo que antes estaba cubierto ahora no.
    inv = compute_coverage_delta(previo, actual)
    assert inv["modules_opened"] == ["c", "d", "e"]
    assert inv["modules_closed"] == []

    # Nunca lanza.
    assert compute_coverage_delta(None, None)["has_previous"] is False


# ---------------------------------------------------------------------------
# Plan 285 F0 — red-team: los defectos MEDIDOS, probados antes de arreglarlos
#
# Regla anti-falso-verde de este bloque: todo assert de AUSENCIA lleva su
# GEMELO de PRESENCIA en el MISMO test. Un `not dest.exists()` pasa por
# accidente si el path esta mal escrito o si apply_proposals rechazo por otro
# motivo; el gemelo prueba que el mecanismo de escritura si funciona.
# ---------------------------------------------------------------------------

def _cuerpo_alucinado(n_lineas: int = 60) -> str:
    """Un documento largo con UNA sola marca y CERO citas archivo:linea.

    Es exactamente el documento que hoy pasa los dos gates y se escribe:
    `marks_ok = any(...)` (doc_documenter.py:190) se conforma con la primera
    linea, y evaluate_citation_gate devuelve passed=True con total==0 (:865).
    """
    lineas = ["[V] Este proyecto tiene una arquitectura modular."]
    lineas += [f"Afirmacion sin respaldo numero {i} sobre el sistema."
               for i in range(n_lineas - 1)]
    return "\n".join(lineas)


def _cuerpo_sano(rel_citada: str) -> str:
    """Documento corto, densamente marcado y con una cita REAL verificable."""
    return "\n".join([
        f"[V] El modulo vive en {rel_citada}:1 y expone su contrato ahi.",
        "[INF] Se infiere que el resto del sistema lo consume por ese contrato.",
        "[NV] No se pudo verificar el historial de cambios.",
    ])


def _props_alucinada_y_sana(rel_citada: str):
    from services.doc_documenter import DocProposal
    mala = DocProposal(path="alucinado.md", action="create",
                       content=_cuerpo_alucinado(), marks_ok=True, sources=[])
    buena = DocProposal(path="sano.md", action="create",
                        content=_cuerpo_sano(rel_citada), marks_ok=True,
                        sources=[rel_citada])
    return mala, buena


def test_f0_documento_sin_citas_y_una_sola_marca_es_rechazado(monkeypatch, tmp_path):
    """K3: hoy un doc de 60 lineas con 1 marca decorativa y 0 citas SE ESCRIBE."""
    from config import config
    from services.doc_documenter import apply_proposals

    ws = tmp_path / "ws"
    (ws / "services").mkdir(parents=True)
    (ws / "services" / "real.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    destino = tmp_path / "out"
    destino.mkdir()

    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED", True, raising=False)
    mala, buena = _props_alucinada_y_sana("services/real.py")
    apply_proposals([mala, buena], str(destino), None, workspace_root=str(ws))

    # AUSENCIA: el alucinado no llega al disco.
    assert not (destino / "alucinado.md").exists(), \
        "el documento alucinado se escribio: el gate de rigor no existe o no corre"
    # GEMELO DE PRESENCIA: el sano SI, en la MISMA llamada.
    assert (destino / "sano.md").exists(), \
        "el documento sano tampoco se escribio: el gate sobre-endurecio"


def test_f0_rigor_rechaza_tambien_sin_workspace_root(monkeypatch, tmp_path):
    """C4: con V2 OFF + citas OFF, run_documenter pasa workspace_root=None
    (doc_documenter.py:1391) y `citations` queda None en todo el loop (:918).
    Un gate colgado de `citations is not None` nace INERTE en produccion
    mientras su test, que fuerza un workspace_root valido, da verde.
    La densidad de marcas NO necesita citas para calcularse."""
    from config import config
    from services.doc_documenter import DocProposal, apply_proposals

    destino = tmp_path / "out"
    destino.mkdir()
    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED", True, raising=False)

    mala = DocProposal(path="alucinado.md", action="create",
                       content=_cuerpo_alucinado(), marks_ok=True, sources=[])
    # El gemelo NO puede pedir citas verificadas: sin workspace_root nadie las
    # cuenta. Lo que prueba es que un doc DENSO en marcas si se escribe.
    denso = DocProposal(
        path="denso.md", action="create",
        content="\n".join(["[V] Primera afirmacion verificada.",
                           "[INF] Segunda afirmacion inferida.",
                           "[NV] Tercera no verificable."]),
        marks_ok=True, sources=[])
    apply_proposals([mala, denso], str(destino), None, workspace_root=None)

    assert not (destino / "alucinado.md").exists(), \
        "sin workspace_root el gate de rigor quedo inerte (defecto C4)"
    assert (destino / "denso.md").exists(), \
        "el doc denso no se escribio: el gate rechaza por falta de citas que no pudo contar"


def test_f0_densidad_de_marcas_por_afirmacion():
    """La funcion nueva del 285. Hoy: ImportError."""
    from services.doc_documenter import evaluate_rigor_gate

    flojo = evaluate_rigor_gate(_cuerpo_alucinado(60), None)
    assert flojo["passed"] is False
    assert flojo["claims"] == 60 and flojo["marked"] == 1

    denso = "\n".join([f"[V] Afirmacion verificada numero {i}." for i in range(6)] +
                      [f"Afirmacion sin marca numero {i}." for i in range(4)])
    fuerte = evaluate_rigor_gate(denso, {"total": 1, "ok": 1, "bad": []})
    assert fuerte["passed"] is True
    assert fuerte["marked"] == 6 and fuerte["claims"] == 10


def test_f0_gate_conserva_el_caso_legitimo_todo_NV():
    """Anti-sobre-endurecimiento: un doc corto e integramente [NV] sigue pasando."""
    from services.doc_documenter import evaluate_rigor_gate

    corto = "\n".join([f"[NV] No se pudo verificar el punto {i}." for i in range(5)])
    out = evaluate_rigor_gate(corto, None)
    assert out["passed"] is True and out["reason"] == ""
    # PRESENCIA: el documento trivial se reconoce como tal, no pasa por casualidad.
    assert out["claims"] == 5


# ---------------------------------------------------------------------------
# Plan 285 F2 — rigor por afirmacion: la tabla de decision completa
# ---------------------------------------------------------------------------

def _doc(n_marcadas: int, n_sueltas: int) -> str:
    return "\n".join([f"[V] Afirmacion verificada {i}." for i in range(n_marcadas)] +
                     [f"Afirmacion sin marca {i}." for i in range(n_sueltas)])


def test_f2_rigor_documento_trivial_pasa():
    from services.doc_documenter import evaluate_rigor_gate
    out = evaluate_rigor_gate(_doc(0, 5), None)
    assert out["passed"] is True and out["claims"] == 5


def test_f2_rigor_densidad_justo_en_el_umbral():
    """La comparacion es `<`: justo en el umbral PASA."""
    from services.doc_documenter import evaluate_rigor_gate
    out = evaluate_rigor_gate(_doc(5, 5), {"total": 1, "ok": 1, "bad": []},
                              min_density=0.5)
    assert out["passed"] is True, f"0.5 no es < 0.5: {out}"
    assert out["density"] == 0.5 and out["claims"] == 10


def test_f2_rigor_densidad_un_pelo_abajo():
    from services.doc_documenter import evaluate_rigor_gate
    out = evaluate_rigor_gate(_doc(4, 6), {"total": 1, "ok": 1, "bad": []},
                              min_density=0.5)
    assert out["passed"] is False
    assert out["reason"].startswith("rigor_density_below:")
    assert out["reason"] == "rigor_density_below:4/10"


def test_f2_rigor_lineas_de_codigo_no_cuentan_como_afirmacion():
    """Sin esto, un doc bien escrito con un ejemplo de codigo pegado se rechaza."""
    from services.doc_documenter import evaluate_rigor_gate

    cuerpo = "\n".join(
        [f"[V] Afirmacion verificada {i}." for i in range(3)] +
        ["```python"] + [f"linea_de_codigo_{i} = {i}" for i in range(40)] + ["```"])
    out = evaluate_rigor_gate(cuerpo, {"total": 1, "ok": 1, "bad": []})
    assert out["passed"] is True, f"el codigo conto como afirmacion: {out}"
    # PRESENCIA: las 3 afirmaciones reales SI se contaron (no dio 0 por error).
    assert out["claims"] == 3 and out["marked"] == 3


def test_f2_rigor_encabezados_no_cuentan():
    from services.doc_documenter import evaluate_rigor_gate

    cuerpo = "\n".join([f"## Seccion {i}" for i in range(20)] +
                       [f"[V] Afirmacion verificada {i}." for i in range(3)])
    out = evaluate_rigor_gate(cuerpo, {"total": 1, "ok": 1, "bad": []})
    assert out["passed"] is True
    assert out["claims"] == 3, f"los encabezados contaron: {out}"


def test_f2_rigor_degrada_ante_basura():
    from services.doc_documenter import evaluate_rigor_gate
    assert evaluate_rigor_gate(None, None)["passed"] is True
    assert evaluate_rigor_gate("", {})["passed"] is True
    assert evaluate_rigor_gate(_doc(0, 60), "no soy un dict")["passed"] is not None


def test_f2_rigor_lee_los_umbrales_de_config(monkeypatch):
    """Sin este test las 2 flags numericas son DECORATIVAS: quedarian
    registradas en el arnes y muertas en el codigo."""
    from config import config
    from services.doc_documenter import evaluate_rigor_gate

    cuerpo = _doc(5, 5)                       # densidad exacta 0.5
    citas = {"total": 1, "ok": 1, "bad": []}

    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_MIN_DENSITY", 0.5, raising=False)
    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_MIN_CITATIONS", 1, raising=False)
    assert evaluate_rigor_gate(cuerpo, citas)["passed"] is True

    # El MISMO documento, con el umbral mas exigente, ahora falla.
    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_MIN_DENSITY", 0.9, raising=False)
    apretado = evaluate_rigor_gate(cuerpo, citas)
    assert apretado["passed"] is False, "la flag de densidad no llega al calculo"
    assert apretado["reason"].startswith("rigor_density_below:")

    # Idem con las citas: mismo doc denso, cero citas validas.
    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_MIN_DENSITY", 0.5, raising=False)
    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_MIN_CITATIONS", 2, raising=False)
    sin_citas = evaluate_rigor_gate(cuerpo, {"total": 1, "ok": 1, "bad": []})
    assert sin_citas["passed"] is False, "la flag de citas minimas no llega al calculo"
    assert sin_citas["reason"] == "rigor_no_citations"


def test_f2_rigor_alcanzable_en_las_4_combinaciones(monkeypatch, tmp_path):
    """C4 — el gate tiene que correr en las CUATRO combinaciones de flags.
    Un ratchet de ORDEN de lineas se cumple igual con el gate inalcanzable."""
    from config import config
    from services.doc_documenter import apply_proposals

    ws = tmp_path / "ws"
    (ws / "services").mkdir(parents=True)
    (ws / "services" / "real.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED", True, raising=False)

    for v2 in (True, False):
        for citas in (True, False):
            monkeypatch.setattr(config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", v2)
            monkeypatch.setattr(config, "STACKY_DOCS_CITATION_GATE_ENABLED", citas)
            destino = tmp_path / f"out_{v2}_{citas}"
            destino.mkdir()
            # El workspace_root se resuelve como en run_documenter, incluida la
            # extension del 285: con las tres flags OFF llegaria None.
            ws_efectivo = str(ws) if (v2 or citas or True) else None
            mala, buena = _props_alucinada_y_sana("services/real.py")
            apply_proposals([mala, buena], str(destino), None,
                            workspace_root=ws_efectivo)
            assert not (destino / "alucinado.md").exists(), \
                f"gate inerte con V2={v2} CITAS={citas}"
            assert (destino / "sano.md").exists(), \
                f"el doc sano se rechazo con V2={v2} CITAS={citas}"


def test_f2_gate_apagado_no_rechaza_nada(monkeypatch, tmp_path):
    """Prueba que la flag es PORTANTE, no decorativa: con OFF vuelve el
    comportamiento de hoy bit a bit (el alucinado se escribe)."""
    from config import config
    from services.doc_documenter import apply_proposals

    ws = tmp_path / "ws"
    (ws / "services").mkdir(parents=True)
    (ws / "services" / "real.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    destino = tmp_path / "out"
    destino.mkdir()

    monkeypatch.setattr(config, "STACKY_DOCS_RIGOR_PER_CLAIM_ENABLED", False, raising=False)
    mala, buena = _props_alucinada_y_sana("services/real.py")
    apply_proposals([mala, buena], str(destino), None, workspace_root=str(ws))

    assert (destino / "alucinado.md").exists(), \
        "con la flag OFF el gate igual rechazo: no es portante, es un cambio duro"
    assert (destino / "sano.md").exists()
