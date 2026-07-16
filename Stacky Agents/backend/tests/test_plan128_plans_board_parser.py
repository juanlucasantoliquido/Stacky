"""Plan 128 F1 — services/plans_board.py: parser puro (tests primero).

Todo con tmp_path; NUNCA contra el docs/ real.
"""
import json

import pytest

from services.plans_board import (
    build_board,
    ledger_info_for,
    load_ledger,
    next_free_number,
    normalize_estado,
    parse_plan_header,
    scan_plan_files,
    suggest_next_action,
    _PLAN_FILE_RE,
)


def _write(path, content):
    path.write_text(content, encoding="utf-8")
    return path


def test_plan_file_re():
    assert _PLAN_FILE_RE.match("95_PLAN_X.md")
    assert _PLAN_FILE_RE.match("126_PLAN_Y.md")
    assert not _PLAN_FILE_RE.match("TOP5_FOO.md")
    assert not _PLAN_FILE_RE.match("25_CHECKLIST_NUEVO_RUNTIME.md")
    assert not _PLAN_FILE_RE.match("9_PLAN_X.md")


def test_scan_no_recursivo(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    _write(docs / "126_PLAN_Y.md", "# Plan 126\n**Estado:** PROPUESTO\n")
    legacy = docs / "_legacy"
    legacy.mkdir()
    _write(legacy / "120_PLAN_A.md", "# Plan 120\n**Estado:** PROPUESTO\n")
    cards = scan_plan_files(docs)
    numbers = {c["number"] for c in cards}
    assert numbers == {126}


@pytest.mark.parametrize(
    "raw_header,expected_estado,expected_veredicto,expected_version,expected_fecha",
    [
        ("# Plan 1\n**Estado:** PROPUESTO (v1)\n", "PROPUESTO", None, "1", None),
        (
            "# Plan 2\n**Estado:** PROPUESTO (v1.1, 2026-07-12 — integra prior art…)\n",
            "PROPUESTO",
            None,
            "1.1",
            "2026-07-12",
        ),
        (
            "# Plan 3\n> **Estado:** IMPLEMENTADO — 2026-07-09 (F0..F6 vía implementar-plan-stacky…)\n",
            "IMPLEMENTADO",
            None,
            None,
            "2026-07-09",
        ),
        (
            "# Plan 4\n> **Estado:** CRITICADO v2 (APROBADO-CON-CAMBIOS) — 2026-07-10\n",
            "CRITICADO",
            "APROBADO-CON-CAMBIOS",
            "2",
            "2026-07-10",
        ),
        (
            "# Plan 5\n> **Estado:** IMPLEMENTADO-PARCIAL — 2026-07-10 (F0-F3…)\n",
            "IMPLEMENTADO_PARCIAL",
            None,
            None,
            "2026-07-10",
        ),
    ],
)
def test_estado_variantes(raw_header, expected_estado, expected_veredicto, expected_version, expected_fecha):
    header = parse_plan_header(raw_header)
    assert header["estado"] == expected_estado
    assert header["veredicto"] == expected_veredicto
    assert header["version"] == expected_version
    assert header["fecha"] == expected_fecha


def test_estado_trampas():
    h1 = parse_plan_header("# Plan X\n**Estado del arte (verificado):** algo\n")
    assert h1["estado"] == "SIN_ESTADO"
    h2 = parse_plan_header("# Plan Y\n**Estado previo:** CRITICADO v2\n")
    assert h2["estado"] == "SIN_ESTADO"


def test_estado_y_previo_juntos():
    text = "# Plan Z\n**Estado:** IMPLEMENTADO — 2026-07-01\n**Estado previo:** CRITICADO v2\n"
    header = parse_plan_header(text)
    assert header["estado"] == "IMPLEMENTADO"


def test_next_free_number_secuencia_compartida(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    _write(docs / "25_CHECKLIST_X.md", "x")
    _write(docs / "126_PLAN_Y.md", "y")
    assert next_free_number(docs) == 127

    docs2 = tmp_path / "docs2"
    docs2.mkdir()
    _write(docs2 / "20_INCIDENTE_Z.md", "z")
    assert next_free_number(docs2) == 21

    docs3 = tmp_path / "docs3"
    docs3.mkdir()
    assert next_free_number(docs3) == 1


def test_duplicados(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    _write(docs / "110_PLAN_A.md", "# A\n**Estado:** PROPUESTO\n")
    _write(docs / "110_PLAN_B.md", "# B\n**Estado:** PROPUESTO\n")
    board = build_board(docs, unpushed_paths=None)
    dup_cards = [c for c in board["plans"] if c["number"] == 110]
    assert len(dup_cards) == 2
    assert all(c["duplicate"] is True for c in dup_cards)
    assert board["totals"]["duplicados"] == 1


def _sha(path):
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_ledger_ok_sin_drift(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = _write(docs / "50_PLAN_X.md", "# Plan 50\n**Estado:** IMPLEMENTADO — 2026-01-01\n")
    sha = _sha(plan_path)
    supervision = docs / "_supervision"
    supervision.mkdir()
    ledger = {"version": 1, "planes": {"50": {"veredicto": "APROBADO", "fecha": "2026-01-01", "doc_sha256": sha}}}
    (supervision / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    loaded = load_ledger(docs)
    info = ledger_info_for(50, plan_path, loaded)
    assert info["doc_drift"] is False

    action_unpushed = suggest_next_action("IMPLEMENTADO", info, True, "50")
    assert action_unpushed["kind"] == "push"
    action_pushed = suggest_next_action("IMPLEMENTADO", info, False, "50")
    assert action_pushed["kind"] == "ok"


def test_ledger_drift(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = _write(docs / "51_PLAN_Y.md", "# Plan 51\n**Estado:** IMPLEMENTADO — 2026-01-01\n")
    supervision = docs / "_supervision"
    supervision.mkdir()
    ledger = {"version": 1, "planes": {"51": {"veredicto": "APROBADO", "fecha": "2026-01-01", "doc_sha256": "0" * 64}}}
    (supervision / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    loaded = load_ledger(docs)
    info = ledger_info_for(51, plan_path, loaded)
    assert info["doc_drift"] is True

    action = suggest_next_action("IMPLEMENTADO", info, False, "51")
    assert action["kind"] == "supervisar"


def test_ledger_sin_sha(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = _write(docs / "81_PLAN_Z.md", "# Plan 81\n**Estado:** IMPLEMENTADO — 2026-01-01\n")
    supervision = docs / "_supervision"
    supervision.mkdir()
    ledger = {"version": 1, "planes": {"81": {"veredicto": "APROBADO", "fecha": "2026-01-01"}}}
    (supervision / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    loaded = load_ledger(docs)
    info = ledger_info_for(81, plan_path, loaded)
    assert info["doc_drift"] is None

    action = suggest_next_action("IMPLEMENTADO", info, False, "81")
    assert action["kind"] == "ok"


def test_ledger_ausente_o_roto(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    assert load_ledger(docs) == {}

    supervision = docs / "_supervision"
    supervision.mkdir()
    (supervision / "ledger.json").write_text("{ esto no es json", encoding="utf-8")
    assert load_ledger(docs) == {}

    docs_utf16 = tmp_path / "docs_utf16"
    docs_utf16.mkdir()
    sup2 = docs_utf16 / "_supervision"
    sup2.mkdir()
    payload = json.dumps({"version": 1, "planes": {"1": {"veredicto": "APROBADO"}}})
    (sup2 / "ledger.json").write_bytes(payload.encode("utf-16"))
    reloaded = load_ledger(docs_utf16)
    assert reloaded.get("1", {}).get("veredicto") == "APROBADO"


@pytest.mark.parametrize(
    "estado,ledger_info,unpushed,expected_kind,expected_command",
    [
        ("IMPLEMENTADO", {"veredicto": "APROBADO", "fecha": "x", "doc_drift": False}, True, "push", "git push"),
        ("IMPLEMENTADO", {"veredicto": "APROBADO", "fecha": "x", "doc_drift": False}, False, "ok", None),
        (
            "IMPLEMENTADO",
            {"veredicto": "APROBADO", "fecha": "x", "doc_drift": True},
            False,
            "supervisar",
            "/supervisar-implementaciones-planes 7",
        ),
        ("PROPUESTO", None, None, "criticar", "/criticar-y-mejorar-plan 7"),
        ("CRITICADO", None, None, "implementar", "/implementar-plan-stacky 7"),
        ("IMPLEMENTADO", None, None, "supervisar", "/supervisar-implementaciones-planes 7"),
        ("IMPLEMENTADO_PARCIAL", None, None, "supervisar", "/supervisar-implementaciones-planes 7"),
        ("SIN_ESTADO", None, None, "revisar", None),
    ],
)
def test_acciones_tabla(estado, ledger_info, unpushed, expected_kind, expected_command):
    action = suggest_next_action(estado, ledger_info, unpushed, "7")
    assert action["kind"] == expected_kind
    assert action["command"] == expected_command


def test_unpushed_none(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = _write(docs / "60_PLAN_X.md", "# Plan 60\n**Estado:** IMPLEMENTADO — 2026-01-01\n")
    supervision = docs / "_supervision"
    supervision.mkdir()
    sha = _sha(plan_path)
    ledger = {"version": 1, "planes": {"60": {"veredicto": "APROBADO", "fecha": "x", "doc_sha256": sha}}}
    (supervision / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")

    board = build_board(docs, unpushed_paths=None)
    card = board["plans"][0]
    assert card["unpushed"] is None
    assert board["totals"]["unpushed"] == 0
    assert card["suggested_action"]["kind"] == "ok"


def test_build_board_orden_y_totales(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    _write(docs / "10_PLAN_A.md", "# A\n**Estado:** PROPUESTO\n")
    _write(docs / "30_PLAN_B.md", "# B\n**Estado:** CRITICADO v1\n")
    _write(docs / "20_PLAN_C.md", "# C\n**Estado:** IMPLEMENTADO — 2026-01-01\n")

    board = build_board(docs, unpushed_paths=None)
    numbers = [c["number"] for c in board["plans"]]
    assert numbers == [30, 20, 10]
    assert board["totals"]["total"] == 3
    assert board["docs_dir_found"] is True
    assert "generated_at" in board and "T" in board["generated_at"]
