"""tests/test_plan237_plans_triage.py — Plan 237: triage, censo y numeración."""
import json
import pathlib
import re


# ── F0 — la flag del inventario nace ON ─────────────────────────────────────
def test_plan237_flag_default_on():
    """La FlagSpec del tablero declara default=True."""
    from services.harness_flags import FLAG_REGISTRY
    spec = next(s for s in FLAG_REGISTRY if s.key == "STACKY_PLANS_BOARD_ENABLED")
    assert spec.default is True


def test_plan237_config_default_on_sin_env():
    """config.py declara "true" como default de la variable de entorno.

    Se verifica sobre el SOURCE y NO con importlib.reload(config): recargar el
    módulo config dentro de una corrida contamina otros tests del arnés (gotcha
    conocido). El source es la única fuente del default y basta para el gate.
    """
    src = pathlib.Path(__file__).resolve().parents[1] / "config.py"
    texto = src.read_text(encoding="utf-8")
    m = re.search(r'os\.getenv\(\s*"STACKY_PLANS_BOARD_ENABLED",\s*"(\w+)"', texto, re.S)
    assert m is not None, "no se encontró el getenv de STACKY_PLANS_BOARD_ENABLED en config.py"
    assert m.group(1) == "true"


# ── F1 — buckets de triage ──────────────────────────────────────────────────
def test_orden_de_buckets_es_el_contratado():
    from services.plans_board import TRIAGE_BUCKETS
    assert [k for k, _ in TRIAGE_BUCKETS] == [
        "SIN_IMPLEMENTAR", "SIN_CRITICAR", "SIN_DOCUMENTO", "SIN_SUPERVISAR", "COMPLETADO",
    ]


def test_mapeo_estado_a_bucket_completo():
    from services.plans_board import triage_bucket
    assert triage_bucket("CRITICADO") == "SIN_IMPLEMENTAR"
    assert triage_bucket("IMPLEMENTADO_PARCIAL") == "SIN_IMPLEMENTAR"
    assert triage_bucket("PROPUESTO") == "SIN_CRITICAR"
    assert triage_bucket("SIN_ESTADO") == "SIN_CRITICAR"
    assert triage_bucket("IMPLEMENTADO") == "SIN_SUPERVISAR"
    assert triage_bucket("APROBADO") == "COMPLETADO"
    assert triage_bucket("MARCIANO") == "SIN_CRITICAR"   # desconocido -> pide revisión
    assert triage_bucket("") == "SIN_CRITICAR"


def test_cobertura_total_de_normalize_estado():
    """Ningún valor que normalize_estado pueda producir queda sin bucket explícito."""
    from services.plans_board import _ESTADO_A_BUCKET
    posibles = {"PROPUESTO", "CRITICADO", "IMPLEMENTADO", "IMPLEMENTADO_PARCIAL",
                "SIN_ESTADO", "APROBADO"}
    assert posibles <= set(_ESTADO_A_BUCKET)


def test_build_board_ordena_por_bucket_y_luego_por_numero(tmp_path):
    """Un plan CRITICADO viejo va ARRIBA de un PROPUESTO nuevo."""
    from services.plans_board import build_board
    (tmp_path / "10_PLAN_VIEJO_CRITICADO.md").write_text(
        "# Viejo\n\n**Estado:** CRITICADO v2 APROBADO 2026-01-01\n", encoding="utf-8")
    (tmp_path / "90_PLAN_NUEVO_PROPUESTO.md").write_text(
        "# Nuevo\n\n**Estado:** PROPUESTO v1 2026-07-25\n", encoding="utf-8")
    (tmp_path / "50_PLAN_MEDIO_IMPLEMENTADO.md").write_text(
        "# Medio\n\n**Estado:** IMPLEMENTADO 2026-05-05\n", encoding="utf-8")
    board = build_board(tmp_path, unpushed_paths=None)
    assert [p["number"] for p in board["plans"]] == [10, 90, 50]
    assert board["triage_order"][0] == "SIN_IMPLEMENTAR"
    assert board["triage_totals"]["SIN_IMPLEMENTAR"] == 1


def test_desempate_dentro_del_bucket_es_numero_descendente(tmp_path):
    from services.plans_board import build_board
    for n in ("11", "22", "33"):
        (tmp_path / f"{n}_PLAN_X{n}.md").write_text(
            f"# X{n}\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    board = build_board(tmp_path, unpushed_paths=None)
    assert [p["number"] for p in board["plans"]] == [33, 22, 11]


def test_claves_legacy_del_plan128_siguen_presentes(tmp_path):
    """G4: aditivo. Ninguna clave del contrato del Plan 128 desaparece."""
    from services.plans_board import build_board
    (tmp_path / "07_PLAN_Z.md").write_text("# Z\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    card = build_board(tmp_path, unpushed_paths=None)["plans"][0]
    for k in ("number", "number_str", "slug", "filename", "path_rel", "title", "estado",
              "estado_raw", "estado_efectivo", "veredicto", "version", "fecha",
              "duplicate", "ledger", "unpushed", "suggested_action"):
        assert k in card, f"clave legacy perdida: {k}"
    assert card["triage_bucket"] == "SIN_CRITICAR"


# ── F2 — censo honesto + escáner acotado y memoizado ────────────────────────
def test_censo_declara_todos_los_excluidos(tmp_path):
    from services.plans_board import build_board
    (tmp_path / "01_PLAN_OK.md").write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    (tmp_path / "02_CHECKLIST_NO_ES_PLAN.md").write_text("# No\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
    legacy = tmp_path / "_legacy"; legacy.mkdir()
    (legacy / "03_PLAN_ARCHIVADO.md").write_text("# Arch\n", encoding="utf-8")
    c = build_board(tmp_path, unpushed_paths=None)["census"]
    assert c["files_seen"] == 3
    assert c["plans_parsed"] == 1
    assert c["skipped_not_a_plan"] == 2
    assert c["skipped_subdirs"] == 1
    assert c["subdir_examples"] == ["_legacy/03_PLAN_ARCHIVADO.md"]
    assert c["skipped_oversize"] == 0 and c["skipped_unreadable"] == 0
    assert c["skipped_over_cap"] == 0


def test_scan_plan_files_conserva_su_firma(tmp_path):
    """G4: el Plan 128 sigue llamando scan_plan_files(dir) -> list."""
    from services.plans_board import scan_plan_files
    (tmp_path / "01_PLAN_OK.md").write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    out = scan_plan_files(tmp_path)
    assert isinstance(out, list) and len(out) == 1 and out[0]["number"] == 1


def test_memo_no_relee_archivos_sin_cambios(tmp_path, monkeypatch):
    """K7: el segundo escaneo del MISMO archivo sin cambios no vuelve a abrir el disco."""
    from services import plans_board as pb
    pb._HEADER_MEMO.clear()
    f = tmp_path / "01_PLAN_OK.md"
    f.write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    aperturas = {"n": 0}
    real_open = pb.Path.open

    def contando(self, *a, **k):
        if self.name.endswith("_PLAN_OK.md"):
            aperturas["n"] += 1
        return real_open(self, *a, **k)

    monkeypatch.setattr(pb.Path, "open", contando)
    pb.scan_plan_files(tmp_path)
    pb.scan_plan_files(tmp_path)
    assert aperturas["n"] == 1, "el memo debe evitar la segunda lectura"


def test_memo_reparsea_cuando_el_archivo_cambia(tmp_path):
    from services import plans_board as pb
    pb._HEADER_MEMO.clear()
    f = tmp_path / "01_PLAN_OK.md"
    f.write_text("# Ok\n\n**Estado:** PROPUESTO\n", encoding="utf-8")
    assert pb.scan_plan_files(tmp_path)[0]["estado"] == "PROPUESTO"
    f.write_text("# Ok\n\n**Estado:** CRITICADO v2\n\n<!-- relleno -->\n", encoding="utf-8")
    assert pb.scan_plan_files(tmp_path)[0]["estado"] == "CRITICADO"


def test_cota_de_archivos_se_declara(tmp_path):
    from services import plans_board as pb
    monkey = pb._MAX_PLAN_FILES
    try:
        pb._MAX_PLAN_FILES = 2
        for n in ("01", "02", "03", "04"):
            (tmp_path / f"{n}_PLAN_X.md").write_text("# X\n", encoding="utf-8")
        c = pb.build_board(tmp_path, unpushed_paths=None)["census"]
        assert c["plans_parsed"] == 2 and c["skipped_over_cap"] == 2
        assert c["plans_parsed"] + c["skipped_over_cap"] == c["files_seen"]
    finally:
        pb._MAX_PLAN_FILES = monkey


def test_censo_de_docs_reales_cierra_la_cuenta():
    """Sobre el docs/ real: la invariante del censo se cumple y hay al menos 3 archivados."""
    from services.plans_board import docs_dir_default, build_board
    c = build_board(docs_dir_default(), unpushed_paths=None)["census"]
    assert (c["plans_parsed"] + c["skipped_not_a_plan"] + c["skipped_oversize"]
            + c["skipped_unreadable"] + c["skipped_over_cap"]) == c["files_seen"]
    assert c["skipped_subdirs"] >= 3    # docs/_legacy/ tiene 3 planes archivados


def test_board_cacheado_no_comparte_estructuras_mutables():
    """C12: mutar el board devuelto NO envenena el cache."""
    from services.plans_board import get_board_cached
    a = get_board_cached()
    a["census"]["files_seen"] = -999
    b = get_board_cached()
    assert b["census"]["files_seen"] != -999


# ── F3 — roadmaps, números reservados y cards SIN_DOCUMENTO ─────────────────
def test_next_free_number_effective_saltea_reservados(tmp_path):
    from services.plans_board import next_free_number, next_free_number_effective
    (tmp_path / "18_PLAN_ORQ.md").write_text("# Orq\n\n**Estado:** IMPLEMENTADO\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps(
        {"subplans": [{"number": 19, "title": "A"}, {"number": 20, "title": "B"}]}), encoding="utf-8")
    assert next_free_number(tmp_path) == 19            # el crudo colisiona
    assert next_free_number_effective(tmp_path) == 21  # el efectivo saltea 19 y 20


def test_sin_roadmap_effective_es_igual_al_crudo(tmp_path):
    from services.plans_board import next_free_number, next_free_number_effective
    (tmp_path / "05_PLAN_A.md").write_text("# A\n", encoding="utf-8")
    assert next_free_number_effective(tmp_path) == next_free_number(tmp_path) == 6


def test_roadmap_corrupto_no_rompe(tmp_path):
    from services.plans_board import load_roadmap_entries, build_board
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "roto.json").write_text("{ esto no es json", encoding="utf-8")
    (rm / "otra_forma.json").write_text('{"cosas": [1,2,3]}', encoding="utf-8")
    (rm / "lista_pelada.json").write_text('[1,2,3]', encoding="utf-8")
    assert load_roadmap_entries(tmp_path) == []
    assert build_board(tmp_path, unpushed_paths=None)["plans"] == []


def test_planes_catalogados_sin_doc_entran_como_SIN_DOCUMENTO(tmp_path):
    from services.plans_board import build_board
    (tmp_path / "18_PLAN_ORQ.md").write_text("# Orq\n\n**Estado:** IMPLEMENTADO\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps({"subplans": [
        {"number": 18, "title": "Ya tiene doc"},
        {"number": 19, "title": "Onboarding GitLab", "priority": "P0", "milestone": "M1"},
    ]}), encoding="utf-8")
    board = build_board(tmp_path, unpushed_paths=None)
    sd = [p for p in board["plans"] if p["triage_bucket"] == "SIN_DOCUMENTO"]
    assert [p["number"] for p in sd] == [19]
    assert sd[0]["suggested_action"]["kind"] == "proponer"
    assert sd[0]["suggested_action"]["command"].startswith("/proponer-plan-stacky ")
    assert sd[0]["suggested_action"]["natural_language"]
    assert board["triage_totals"]["SIN_DOCUMENTO"] == 1


def test_docs_reales_proponen_un_numero_libre_de_verdad():
    """Sobre el docs/ real. RELATIVO: no hardcodea 237 ni 239 (caducan al día siguiente)."""
    from services.plans_board import (docs_dir_default, build_board, reserved_numbers)
    docs = docs_dir_default()
    board = build_board(docs, unpushed_paths=None)
    n = board["next_free_number"]
    con_doc = {p["number"] for p in board["plans"] if p["filename"]}
    assert n not in reserved_numbers(docs), "propuso un número RESERVADO por un roadmap"
    assert n not in con_doc, "propuso un número que YA tiene documento"
    assert n > max(con_doc), "el número propuesto debe ser mayor que todos los existentes"


def test_docs_reales_listan_los_subplanes_218_sin_doc():
    from services.plans_board import docs_dir_default, build_board
    board = build_board(docs_dir_default(), unpushed_paths=None)
    sd = {p["number"] for p in board["plans"] if p["triage_bucket"] == "SIN_DOCUMENTO"}
    assert 219 in sd and 236 in sd, "faltan subplanes reservados de la serie 218"
    assert 218 not in sd, "el 218 tiene documento: no puede figurar como SIN_DOCUMENTO"


# ── F7 — guardia de numeración anti-colisión ────────────────────────────────
def test_universo_de_numeros_cubre_las_cuatro_fuentes(tmp_path):
    from services.plans_board import all_claimed_numbers
    (tmp_path / "05_PLAN_A.md").write_text("# A\n", encoding="utf-8")
    leg = tmp_path / "_legacy"; leg.mkdir()
    (leg / "07_PLAN_VIEJO.md").write_text("# V\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps({"subplans": [{"number": 9, "title": "X"}]}), encoding="utf-8")
    f = all_claimed_numbers(tmp_path)
    assert 5 in f["root"] and 7 in f["subdirs"] and 9 in f["roadmap"]


def test_next_free_salta_por_encima_de_todas_las_fuentes(tmp_path):
    from services.plans_board import next_free_number_effective
    (tmp_path / "05_PLAN_A.md").write_text("# A\n", encoding="utf-8")
    rm = tmp_path / "_roadmap"; rm.mkdir()
    (rm / "serie.json").write_text(json.dumps({"subplans": [{"number": 9, "title": "X"}]}), encoding="utf-8")
    assert next_free_number_effective(tmp_path) == 10   # no 6: el 9 está comprometido


def test_duplicados_se_detectan_con_nombres(tmp_path):
    from services.plans_board import plan_number_duplicates, build_board
    (tmp_path / "37_PLAN_UNO.md").write_text("# Uno\n", encoding="utf-8")
    (tmp_path / "37_PLAN_DOS.md").write_text("# Dos\n", encoding="utf-8")
    (tmp_path / "38_PLAN_SOLO.md").write_text("# Solo\n", encoding="utf-8")
    dups = plan_number_duplicates(tmp_path)
    assert [d["number"] for d in dups] == [37]
    assert dups[0]["filenames"] == ["37_PLAN_DOS.md", "37_PLAN_UNO.md"]
    assert build_board(tmp_path, unpushed_paths=None)["numbering"]["duplicates"] == dups


def test_sin_duplicados_la_lista_esta_vacia(tmp_path):
    from services.plans_board import plan_number_duplicates
    (tmp_path / "37_PLAN_UNO.md").write_text("# Uno\n", encoding="utf-8")
    assert plan_number_duplicates(tmp_path) == []


def test_claim_plan_path_es_exclusivo(tmp_path):
    import pytest as _pytest
    from services.plans_board import claim_plan_path
    p = claim_plan_path(tmp_path, 40, "40_PLAN_X.md")
    assert p.exists()
    with _pytest.raises(FileExistsError):
        claim_plan_path(tmp_path, 40, "40_PLAN_X.md")   # la segunda sesión NO pisa


def test_docs_reales_sin_numeros_duplicados():
    """GUARD (huella plan-number-collision-2026-07-25). Hoy VERDE: la colisión 237/238
    ya se resolvió renumerando. Si vuelve a aparecer un NN repetido, este test se pone
    rojo y nombra los archivos."""
    from services.plans_board import docs_dir_default, plan_number_duplicates
    dups = plan_number_duplicates(docs_dir_default())
    assert dups == [], f"números de plan duplicados en docs/: {dups}"
