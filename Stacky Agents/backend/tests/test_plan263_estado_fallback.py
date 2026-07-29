"""Plan 263 F1 — resolve_estado() y el fallback único de estado.

Test-first (TDD): este archivo se escribe ANTES de tocar services/plans_board.py.
Casos 1-19 tal cual la tabla de la fase F1 del plan (v6, LISTO PARA IMPLEMENTAR).

No toca la DB (funciones puras + tmp_path): no es flaky, no necesita run_with_retry.
Correr SOLO este archivo, nunca la suite completa (contaminación cross-run conocida).
"""
import hashlib
import json
import pathlib
import sys

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import config  # noqa: E402
from services.plans_board import (  # noqa: E402
    build_board,
    build_planned_cards,
    resolve_estado,
    suggest_next_action,
)


def _write(tmp_path: pathlib.Path, filename: str, body: str) -> None:
    # newline="" evita que Windows traduzca "\n" -> "\r\n" al escribir: el sha256
    # calculado sobre `body.encode("utf-8")` tiene que ser el sha256 REAL del
    # archivo en disco (ledger_info_for lee con path.read_bytes()).
    (tmp_path / filename).write_text(body, encoding="utf-8", newline="")


def _write_ledger(tmp_path: pathlib.Path, entries: dict) -> None:
    (tmp_path / "_supervision").mkdir(exist_ok=True)
    (tmp_path / "_supervision" / "ledger.json").write_text(
        json.dumps({"version": 1, "planes": entries}), encoding="utf-8"
    )


# ── Casos 1-8: resolve_estado() puro ────────────────────────────────────────

def test_case1_resolve_estado_propuesto():
    assert resolve_estado("PROPUESTO") == ("PROPUESTO", False)


def test_case2_resolve_estado_criticado():
    assert resolve_estado("CRITICADO") == ("CRITICADO", False)


def test_case3_resolve_estado_implementado():
    assert resolve_estado("IMPLEMENTADO") == ("IMPLEMENTADO", False)


def test_case4_resolve_estado_implementado_parcial():
    assert resolve_estado("IMPLEMENTADO_PARCIAL") == ("IMPLEMENTADO_PARCIAL", False)


def test_case5_resolve_estado_sin_estado_cae_a_fallback():
    assert resolve_estado("SIN_ESTADO") == ("IMPLEMENTADO", True)


def test_case6_resolve_estado_vacio_cae_a_fallback():
    assert resolve_estado("") == ("IMPLEMENTADO", True)


def test_case7_resolve_estado_none_no_lanza():
    assert resolve_estado(None) == ("IMPLEMENTADO", True)


def test_case8_resolve_estado_basura_cae_a_fallback():
    assert resolve_estado("BASURA_NO_RECONOCIDA") == ("IMPLEMENTADO", True)


# ── Casos 9-11: build_board sobre un .md SIN **Estado:** ────────────────────

def test_case9_build_board_doc_sin_estado_infiere_implementado(tmp_path):
    _write(tmp_path, "07_PLAN_SIN_ESTADO.md", "# Plan 07 — sin estado\n\nCuerpo sin linea de estado.\n")
    board = build_board(tmp_path, None)
    card = board["plans"][0]
    assert card["estado_efectivo"] == "IMPLEMENTADO"
    assert card["estado_inferido"] is True
    assert card["estado_origen"] == "inferido"
    assert card["triage_bucket"] == "SIN_SUPERVISAR"


def test_case10_build_board_doc_sin_estado_sugiere_supervisar(tmp_path):
    _write(tmp_path, "07_PLAN_SIN_ESTADO.md", "# Plan 07 — sin estado\n\nCuerpo sin linea de estado.\n")
    board = build_board(tmp_path, None)
    card = board["plans"][0]
    assert card["suggested_action"]["kind"] == "supervisar"


def test_case11_build_board_doc_sin_estado_avisa_en_la_sugerencia(tmp_path):
    _write(tmp_path, "07_PLAN_SIN_ESTADO.md", "# Plan 07 — sin estado\n\nCuerpo sin linea de estado.\n")
    board = build_board(tmp_path, None)
    card = board["plans"][0]
    assert "no declara" in card["suggested_action"]["natural_language"]


# ── Caso 12: doc CON **Estado:** ─────────────────────────────────────────────

def test_case12_build_board_doc_con_estado_declarado(tmp_path):
    _write(tmp_path, "08_PLAN_CON_ESTADO.md", "# Plan 08 — con estado\n\n**Estado:** PROPUESTO v1\n")
    board = build_board(tmp_path, None)
    card = board["plans"][0]
    assert card["estado_inferido"] is False
    assert card["estado_origen"] == "declarado"
    assert card["estado_efectivo"] == "PROPUESTO"


# ── Caso 13 (v3/C3): doc sin estado PERO aprobado en el ledger sin drift ────

def test_case13_build_board_doc_sin_estado_pero_ledger_aprobado(tmp_path):
    body = "# Plan 09 — aprobado por el ledger\n\nCuerpo sin linea de estado.\n"
    _write(tmp_path, "09_PLAN_LEDGER.md", body)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    _write_ledger(tmp_path, {"9": {"plan": 9, "veredicto": "APROBADO", "doc_sha256": sha}})
    board = build_board(tmp_path, None)
    card = board["plans"][0]
    assert card["estado_efectivo"] == "APROBADO"
    assert card["estado_origen"] == "ledger"
    assert card["estado_inferido"] is False


# ── Caso 14: totales sobre 3 docs sin estado ────────────────────────────────

def test_case14_build_board_totales_sin_estado_y_contador_inferidos(tmp_path):
    for i in range(3):
        _write(tmp_path, f"{10 + i:02d}_PLAN_X{i}.md", f"# Plan {10 + i}\n\nsin estado.\n")
    board = build_board(tmp_path, None)
    assert "SIN_ESTADO" not in board["totals"]
    assert board["totals"]["inferidos"] == 3


# ── Caso 15: flag OFF — comportamiento byte-idéntico al previo al Plan 263 ──

def test_case15_build_board_flag_off_conserva_comportamiento_previo(tmp_path, monkeypatch):
    _write(tmp_path, "07_PLAN_SIN_ESTADO.md", "# Plan 07 — sin estado\n\nCuerpo sin linea de estado.\n")
    monkeypatch.setattr(config.config, "STACKY_PLANS_ESTADO_FALLBACK_ENABLED", False)
    board = build_board(tmp_path, None)
    card = board["plans"][0]
    assert card["estado_efectivo"] == "SIN_ESTADO"
    assert card["estado_inferido"] is False
    assert card["estado_origen"] == "declarado"
    assert card["suggested_action"]["kind"] == "revisar"


# ── Caso 16 (v2): build_planned_cards trae la misma forma ───────────────────

def test_case16_build_planned_cards_forma_uniforme(tmp_path):
    roadmap_dir = tmp_path / "_roadmap"
    roadmap_dir.mkdir()
    (roadmap_dir / "catalogo.json").write_text(
        json.dumps({"subplans": [{"number": 900, "title": "Futuro"}]}), encoding="utf-8"
    )
    cards = build_planned_cards(tmp_path, set())
    assert len(cards) == 1
    for c in cards:
        assert c["estado_inferido"] is False
        assert c["estado_origen"] == "declarado"


# ── Caso 17: suggest_next_action posicional con 4 args (keyword-only nuevo) ─

def test_case17_suggest_next_action_posicional_4_args_no_lanza():
    result = suggest_next_action("IMPLEMENTADO", None, None, "07")
    assert result["kind"] == "supervisar"


# ── Caso 18 (v3/C3 — INVARIANTE): las 4 formas de card a la vez ─────────────

def test_case18_build_board_invariante_estado_inferido_coincide_con_origen(tmp_path):
    _write(tmp_path, "01_PLAN_DECLARADO.md", "# Plan 01\n\n**Estado:** PROPUESTO v1\n")
    _write(tmp_path, "02_PLAN_INFERIDO.md", "# Plan 02\n\nsin estado.\n")
    body3 = "# Plan 03 — aprobado\n\nsin estado.\n"
    _write(tmp_path, "03_PLAN_LEDGER.md", body3)
    sha3 = hashlib.sha256(body3.encode("utf-8")).hexdigest()
    _write_ledger(tmp_path, {"3": {"plan": 3, "veredicto": "APROBADO", "doc_sha256": sha3}})
    roadmap_dir = tmp_path / "_roadmap"
    roadmap_dir.mkdir()
    (roadmap_dir / "catalogo.json").write_text(
        json.dumps({"subplans": [{"number": 900, "title": "Futuro"}]}), encoding="utf-8"
    )

    board = build_board(tmp_path, None)
    assert len(board["plans"]) == 4
    for card in board["plans"]:
        assert card["estado_inferido"] == (card["estado_origen"] == "inferido")
        assert card["estado_origen"] in ("declarado", "inferido", "ledger")


# ── Caso 19 [v4/ADICIÓN 6]: totals["por_origen"] particiona completo ────────

def test_case19_build_board_totales_por_origen_particion_completa(tmp_path):
    _write(tmp_path, "01_PLAN_DECLARADO.md", "# Plan 01\n\n**Estado:** PROPUESTO v1\n")
    _write(tmp_path, "02_PLAN_INFERIDO.md", "# Plan 02\n\nsin estado.\n")
    body3 = "# Plan 03 — aprobado\n\nsin estado.\n"
    _write(tmp_path, "03_PLAN_LEDGER.md", body3)
    sha3 = hashlib.sha256(body3.encode("utf-8")).hexdigest()
    _write_ledger(tmp_path, {"3": {"plan": 3, "veredicto": "APROBADO", "doc_sha256": sha3}})
    roadmap_dir = tmp_path / "_roadmap"
    roadmap_dir.mkdir()
    (roadmap_dir / "catalogo.json").write_text(
        json.dumps({"subplans": [{"number": 900, "title": "Futuro"}]}), encoding="utf-8"
    )

    board = build_board(tmp_path, None)
    assert sum(board["totals"]["por_origen"].values()) == len(board["plans"])
