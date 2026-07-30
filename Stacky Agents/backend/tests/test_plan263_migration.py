"""Plan 263 F3 + F2.5 — normalización de estado con evidencia (preview + apply).

Test-first (TDD): este archivo se escribe ANTES de tocar
services/plans_estado_migration.py y api/plans_board.py. Casos 1-25 tal cual
la lista de la fase F3 del plan (v6, LISTO PARA IMPLEMENTAR).
"""
import hashlib
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

import services.plans_board as plans_board  # noqa: E402
import services.plans_estado_migration as pem  # noqa: E402
from services.plans_board import parse_plan_header  # noqa: E402
from services.plans_estado_migration import (  # noqa: E402
    apply_estado_migration,
    infer_estado_con_evidencia,
    preview_estado_migration,
)


def _write(tmp_path: pathlib.Path, filename: str, body: str) -> None:
    (tmp_path / filename).write_text(body, encoding="utf-8", newline="")


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _write_ledger_raw(tmp_path: pathlib.Path, data: dict) -> None:
    (tmp_path / "_supervision").mkdir(exist_ok=True)
    (tmp_path / "_supervision" / "ledger.json").write_text(
        json.dumps(data), encoding="utf-8", newline=""
    )


def _write_ledger_text(tmp_path: pathlib.Path, text: str) -> None:
    (tmp_path / "_supervision").mkdir(exist_ok=True)
    (tmp_path / "_supervision" / "ledger.json").write_text(text, encoding="utf-8", newline="")


@pytest.fixture
def baseline_hermetico(tmp_path, monkeypatch):
    """Aísla TODOS los tests de apply (dry_run=False) del baseline REAL del
    repo (backend/tests/plans_estado_baseline.json, hoy con 79 entradas
    reales): un test JAMÁS debe escribir en ese archivo compartido."""
    fake = tmp_path / "_fake_baseline.json"
    fake.write_text(json.dumps({"sin_estado": []}), encoding="utf-8")
    monkeypatch.setattr(pem, "_BASELINE_PATH", fake)
    return fake


# ── Caso 1 ───────────────────────────────────────────────────────────────────

def test_case1_infer_ledger_aprobado_con_drift(tmp_path):
    body = "# Plan 20 — aprobado por ledger\n\nsin marcador especial.\n"
    _write(tmp_path, "20_PLAN_LEDGER_DRIFT.md", body)
    _write_ledger_raw(tmp_path, {"planes": {"20": {
        "veredicto": "APROBADO", "doc_sha256": "0" * 64, "fecha": "2026-01-01",
    }}})
    r = infer_estado_con_evidencia({"number": 20, "filename": "20_PLAN_LEDGER_DRIFT.md"}, tmp_path)
    assert r["estado_propuesto"] == "IMPLEMENTADO"
    assert r["confianza"] == "alta"
    assert r["aplicable"] is True


# ── Caso 2 ───────────────────────────────────────────────────────────────────

def test_case2_infer_registro_de_implementacion(tmp_path):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo, tests verdes.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    r = infer_estado_con_evidencia({"number": 21, "filename": "21_PLAN_REGISTRO.md"}, tmp_path)
    assert r["estado_propuesto"] == "IMPLEMENTADO"
    assert r["confianza"] == "alta"


# ── Caso 3 ───────────────────────────────────────────────────────────────────

def test_case3_infer_veredicto_aprobado(tmp_path):
    body = "# Plan 22 — revisado\n\nEl veredicto del juez fue APROBADO en la primera ronda.\n"
    _write(tmp_path, "22_PLAN_VEREDICTO.md", body)
    r = infer_estado_con_evidencia({"number": 22, "filename": "22_PLAN_VEREDICTO.md"}, tmp_path)
    assert r["estado_propuesto"] == "CRITICADO"
    assert r["confianza"] == "media"


# ── Caso 4 (v3/C9) ───────────────────────────────────────────────────────────

def test_case4_infer_subcadena_implementada_no_matchea(tmp_path):
    body = "# Plan 23 — sospechoso\n\nla fase NO fue IMPLEMENTADA todavia, ver bitacora.\n"
    _write(tmp_path, "23_PLAN_SOSPECHOSO.md", body)
    r = infer_estado_con_evidencia({"number": 23, "filename": "23_PLAN_SOSPECHOSO.md"}, tmp_path)
    assert r["confianza"] == "sin_evidencia"
    assert r["estado_propuesto"] is None


# ── Caso 5 (v3/C1) ───────────────────────────────────────────────────────────

def test_case5_infer_sin_ninguna_senal(tmp_path):
    _write(tmp_path, "24_PLAN_VACIO.md", "# Plan 24 — nada\n\nsolo texto plano.\n")
    preview = preview_estado_migration(tmp_path)
    assert "baja" not in preview["por_confianza"]
    p = preview["propuestas"][0]
    assert p["confianza"] == "sin_evidencia"
    assert p["estado_propuesto"] is None
    assert p["linea_a_insertar"] is None
    assert p["aplicable"] is False


# ── Caso 6 ───────────────────────────────────────────────────────────────────

def test_case6_linea_a_insertar_forma(tmp_path):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    r = infer_estado_con_evidencia({"number": 21, "filename": "21_PLAN_REGISTRO.md"}, tmp_path)
    assert r["linea_a_insertar"].startswith("**Estado:** ")
    assert "Plan 263" in r["linea_a_insertar"]


# ── Caso 7 ───────────────────────────────────────────────────────────────────

def test_case7_insert_after_line_apunta_al_titulo(tmp_path):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    r = infer_estado_con_evidencia({"number": 21, "filename": "21_PLAN_REGISTRO.md"}, tmp_path)
    lineas = body.splitlines()
    assert lineas[r["insert_after_line"]].startswith("# ")


# ── Caso 8 ───────────────────────────────────────────────────────────────────

def test_case8_preview_no_escribe_nada(tmp_path):
    nombres = []
    for i in range(3):
        n = f"{30 + i}_PLAN_PREVIEW{i}.md"
        _write(tmp_path, n, f"# Plan {30 + i}\n\nsin estado.\n")
        nombres.append(n)
    antes = {n: (tmp_path / n).stat().st_mtime_ns for n in nombres}

    preview = preview_estado_migration(tmp_path)

    despues = {n: (tmp_path / n).stat().st_mtime_ns for n in nombres}
    assert preview["total"] == 3
    assert antes == despues


# ── Caso 9 ───────────────────────────────────────────────────────────────────

def test_case9_apply_dry_run_no_escribe(tmp_path):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    sha = _sha(body)

    r = apply_estado_migration(
        tmp_path, [{"filename": "21_PLAN_REGISTRO.md", "sha256_visto": sha}], dry_run=True
    )
    assert r["aplicados"] == []
    assert r["diffs"]
    assert _sha((tmp_path / "21_PLAN_REGISTRO.md").read_text(encoding="utf-8")) == sha


# ── Caso 10 ──────────────────────────────────────────────────────────────────

def test_case10_apply_real_escribe_estado(tmp_path, baseline_hermetico):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    sha = _sha(body)

    r = apply_estado_migration(
        tmp_path, [{"filename": "21_PLAN_REGISTRO.md", "sha256_visto": sha}], dry_run=False
    )
    assert r["aplicados"] == ["21_PLAN_REGISTRO.md"]
    nuevo_texto = (tmp_path / "21_PLAN_REGISTRO.md").read_text(encoding="utf-8")
    assert "**Estado:**" in nuevo_texto
    header = parse_plan_header(nuevo_texto[:4000])
    assert header["estado"] == "IMPLEMENTADO"


# ── Caso 11 ──────────────────────────────────────────────────────────────────

def test_case11_idempotencia(tmp_path, baseline_hermetico):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    sha = _sha(body)
    apply_estado_migration(
        tmp_path, [{"filename": "21_PLAN_REGISTRO.md", "sha256_visto": sha}], dry_run=False
    )
    sha_normalizado = _sha((tmp_path / "21_PLAN_REGISTRO.md").read_text(encoding="utf-8"))

    r2 = apply_estado_migration(
        tmp_path,
        [{"filename": "21_PLAN_REGISTRO.md", "sha256_visto": sha_normalizado}],
        dry_run=False,
    )
    assert r2["aplicados"] == []
    assert r2["omitidos"][0]["razon"] == "ya declara estado"
    assert _sha((tmp_path / "21_PLAN_REGISTRO.md").read_text(encoding="utf-8")) == sha_normalizado


# ── Caso 12 ──────────────────────────────────────────────────────────────────

def test_case12_seguridad_path_traversal(tmp_path, baseline_hermetico):
    r = apply_estado_migration(
        tmp_path, [{"filename": "../../.env", "sha256_visto": "x"}], dry_run=False
    )
    assert r["ok"] is True
    assert r["aplicados"] == []
    assert r["omitidos"][0]["filename"] == "../../.env"
    assert not (tmp_path.parent.parent / ".env").exists()


# ── Caso 13 (v2/C7 TOCTOU) ───────────────────────────────────────────────────

def test_case13_toctou_cambio_en_disco(tmp_path, baseline_hermetico):
    body = "# Plan 21 — hecho\n\n## Registro de implementación\n\nTodo listo.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body)
    sha_viejo = _sha(body)

    body_editado = body + "\nUna linea mas, editada a mano.\n"
    _write(tmp_path, "21_PLAN_REGISTRO.md", body_editado)

    r = apply_estado_migration(
        tmp_path, [{"filename": "21_PLAN_REGISTRO.md", "sha256_visto": sha_viejo}], dry_run=False
    )
    assert r["aplicados"] == []
    assert r["omitidos"][0]["razon"] == "cambio en disco desde la vista previa"
    assert (tmp_path / "21_PLAN_REGISTRO.md").read_text(encoding="utf-8") == body_editado


# ── Caso 14 (v2/C6 re-sellado, KPI-6) ────────────────────────────────────────

def test_case14_resellado_sin_drift_kpi6(tmp_path, baseline_hermetico):
    body = "# Plan 25 — aprobado sin drift\n\nsin linea de estado.\n"
    _write(tmp_path, "25_PLAN_RESELLO.md", body)
    sha_original = _sha(body)
    _write_ledger_raw(tmp_path, {"version": 1, "planes": {"25": {
        "plan": 25, "veredicto": "APROBADO", "doc_sha256": sha_original, "fecha": "2026-01-01",
    }}})

    r = apply_estado_migration(
        tmp_path, [{"filename": "25_PLAN_RESELLO.md", "sha256_visto": sha_original}], dry_run=False
    )
    assert r["aplicados"] == ["25_PLAN_RESELLO.md"]
    assert r["ledger_resellado"] == ["25_PLAN_RESELLO.md"]

    ledger = plans_board.load_ledger(tmp_path)
    path = tmp_path / "25_PLAN_RESELLO.md"
    info = plans_board.ledger_info_for(25, path, ledger)
    assert info["doc_drift"] is False

    board = plans_board.build_board(tmp_path, None)
    card = [c for c in board["plans"] if c["number"] == 25][0]
    assert card["estado_efectivo"] == "APROBADO"


# ── Caso 15 (v2/C6 sin ledger) ───────────────────────────────────────────────

def test_case15_sin_ledger_no_se_toca(tmp_path, baseline_hermetico):
    body = "# Plan 26 — sin ledger\n\n## Registro de implementación\n\nlisto.\n"
    _write(tmp_path, "26_PLAN_SINLEDGER.md", body)
    sha = _sha(body)
    # ledger.json existe pero es de OTRO plan, ajeno a este apply.
    _write_ledger_raw(tmp_path, {"version": 1, "planes": {"99": {
        "plan": 99, "veredicto": "APROBADO", "doc_sha256": "f" * 64, "fecha": "2026-01-01",
    }}})
    ledger_path = tmp_path / "_supervision" / "ledger.json"
    sha_ledger_antes = _sha(ledger_path.read_text(encoding="utf-8"))

    r = apply_estado_migration(
        tmp_path, [{"filename": "26_PLAN_SINLEDGER.md", "sha256_visto": sha}], dry_run=False
    )
    assert r["aplicados"] == ["26_PLAN_SINLEDGER.md"]
    assert r["ledger_resellado"] == []
    assert _sha(ledger_path.read_text(encoding="utf-8")) == sha_ledger_antes


# ── Caso 16 (v2/C10 poda) ────────────────────────────────────────────────────

def test_case16_poda_del_baseline(tmp_path, baseline_hermetico):
    body = "# Plan 27 — a podar\n\n## Registro de implementación\n\nlisto.\n"
    _write(tmp_path, "27_PLAN_PODAR.md", body)
    sha = _sha(body)
    baseline_hermetico.write_text(
        json.dumps({"sin_estado": ["27_PLAN_PODAR.md", "28_PLAN_OTRO.md"]}), encoding="utf-8"
    )

    r = apply_estado_migration(
        tmp_path, [{"filename": "27_PLAN_PODAR.md", "sha256_visto": sha}], dry_run=False
    )
    assert r["baseline_podado"] == ["27_PLAN_PODAR.md"]
    data = json.loads(baseline_hermetico.read_text(encoding="utf-8"))
    assert "27_PLAN_PODAR.md" not in data["sin_estado"]
    assert "28_PLAN_OTRO.md" in data["sin_estado"]


# ── Caso 17 (rollback: ledger corrupto) ──────────────────────────────────────

def test_case17_rollback_ledger_corrupto(tmp_path, baseline_hermetico):
    body = "# Plan 28 — rollback\n\n## Registro de implementación\n\nlisto.\n"
    _write(tmp_path, "28_PLAN_ROLLBACK.md", body)
    sha = _sha(body)
    _write_ledger_text(tmp_path, "esto no es json {{{")

    r = apply_estado_migration(
        tmp_path, [{"filename": "28_PLAN_ROLLBACK.md", "sha256_visto": sha}], dry_run=False
    )
    assert r["aplicados"] == []
    assert r["omitidos"][0]["razon"].startswith("rollback")
    assert (tmp_path / "28_PLAN_ROLLBACK.md").read_text(encoding="utf-8") == body


# ── Caso 18 (v2/C14 cache) ───────────────────────────────────────────────────

def test_case18_invalida_cache(tmp_path, baseline_hermetico, monkeypatch):
    body = "# Plan 29 — cache\n\n## Registro de implementación\n\nlisto.\n"
    _write(tmp_path, "29_PLAN_CACHE.md", body)
    sha = _sha(body)
    monkeypatch.setattr(plans_board, "_BOARD_CACHE", (0.0, {"fake": True}))

    apply_estado_migration(
        tmp_path, [{"filename": "29_PLAN_CACHE.md", "sha256_visto": sha}], dry_run=False
    )
    assert plans_board._BOARD_CACHE is None


# ── Caso 19 (v3/C5 el ledger sobrevive entero) ───────────────────────────────

def test_case19_ledger_sobrevive_entero(tmp_path, baseline_hermetico):
    body7 = "# Plan 7 — normalizar\n\n## Registro de implementación\n\nlisto.\n"
    _write(tmp_path, "07_PLAN_SEVEN.md", body7)
    sha7 = _sha(body7)
    ledger_original = {
        "version": 1,
        "planes": {
            "7": {"plan": 7, "ruta": "docs/07_PLAN_SEVEN.md", "veredicto": "CRITICADO",
                  "fecha": "2026-01-01", "doc_sha256": sha7},
            "8": {"plan": 8, "ruta": "docs/08_PLAN_EIGHT.md", "veredicto": "APROBADO",
                  "fecha": "2026-01-02", "doc_sha256": "f" * 64},
        },
    }
    _write_ledger_raw(tmp_path, ledger_original)

    r = apply_estado_migration(
        tmp_path, [{"filename": "07_PLAN_SEVEN.md", "sha256_visto": sha7}], dry_run=False
    )
    assert r["ledger_resellado"] == ["07_PLAN_SEVEN.md"]

    data = json.loads((tmp_path / "_supervision" / "ledger.json").read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert set(data["planes"]) == {"7", "8"}
    assert json.dumps(data["planes"]["8"], sort_keys=True) == json.dumps(
        ledger_original["planes"]["8"], sort_keys=True
    )
    entry7 = data["planes"]["7"]
    assert entry7["plan"] == 7
    assert entry7["ruta"] == "docs/07_PLAN_SEVEN.md"
    assert entry7["veredicto"] == "CRITICADO"
    assert entry7["fecha"] == "2026-01-01"
    assert entry7["doc_sha256"] != sha7
    assert entry7["normalizado_por"] == "plan-263"
    assert "normalizado_en" in entry7


# ── Caso 20 (v3/C5 el ledger sin envoltorio no se "repara") ──────────────────

def test_case20a_ledger_sin_version_no_se_inventa(tmp_path, baseline_hermetico):
    body = "# Plan 9 — sin version\n\nsin linea de estado.\n"
    _write(tmp_path, "09_PLAN_SINVERSION.md", body)
    sha = _sha(body)
    _write_ledger_raw(tmp_path, {"planes": {"9": {
        "veredicto": "APROBADO", "doc_sha256": sha, "fecha": "2026-01-01",
    }}})

    r = apply_estado_migration(
        tmp_path, [{"filename": "09_PLAN_SINVERSION.md", "sha256_visto": sha}], dry_run=False
    )
    assert r["aplicados"] == ["09_PLAN_SINVERSION.md"]
    data = json.loads((tmp_path / "_supervision" / "ledger.json").read_text(encoding="utf-8"))
    assert "version" not in data
    assert data["planes"]["9"]["doc_sha256"] != sha


def test_case20b_ledger_sin_planes_rollback(tmp_path, baseline_hermetico):
    body = "# Plan 10 — sin planes\n\n## Registro de implementación\n\nlisto.\n"
    _write(tmp_path, "10_PLAN_SINPLANES.md", body)
    sha = _sha(body)
    _write_ledger_raw(tmp_path, {"otra_cosa": 1})

    r = apply_estado_migration(
        tmp_path, [{"filename": "10_PLAN_SINPLANES.md", "sha256_visto": sha}], dry_run=False
    )
    assert r["aplicados"] == []
    assert r["omitidos"][0]["razon"].startswith("rollback")
    assert (tmp_path / "10_PLAN_SINPLANES.md").read_text(encoding="utf-8") == body


# ── Caso 21 (v3/ADICIÓN 4) ───────────────────────────────────────────────────

def test_case21_rechaza_sin_evidencia_y_sin_elegido_luego_acepta_elegido(tmp_path, baseline_hermetico):
    body = "# Plan 31 — sin nada\n\ntexto plano sin marcadores.\n"
    _write(tmp_path, "31_PLAN_SINEVIDENCIA.md", body)
    sha = _sha(body)

    r1 = apply_estado_migration(
        tmp_path, [{"filename": "31_PLAN_SINEVIDENCIA.md", "sha256_visto": sha}], dry_run=False
    )
    assert r1["aplicados"] == []
    assert r1["omitidos"][0]["razon"] == "sin evidencia y sin estado elegido por el operador"
    assert _sha((tmp_path / "31_PLAN_SINEVIDENCIA.md").read_text(encoding="utf-8")) == sha

    r2 = apply_estado_migration(
        tmp_path,
        [{"filename": "31_PLAN_SINEVIDENCIA.md", "sha256_visto": sha, "estado_elegido": "PROPUESTO"}],
        dry_run=False,
    )
    assert r2["aplicados"] == ["31_PLAN_SINEVIDENCIA.md"]
    nuevo = (tmp_path / "31_PLAN_SINEVIDENCIA.md").read_text(encoding="utf-8")
    assert "elegido por el operador" in nuevo


# ── Caso 22 (v3/ADICIÓN 4 vocabulario cerrado) ───────────────────────────────

def test_case22_estado_elegido_invalido(tmp_path, baseline_hermetico):
    body = "# Plan 32 — vocabulario\n\ntexto plano.\n"
    _write(tmp_path, "32_PLAN_VOCAB.md", body)
    sha = _sha(body)

    r = apply_estado_migration(
        tmp_path,
        [{"filename": "32_PLAN_VOCAB.md", "sha256_visto": sha, "estado_elegido": "LO_QUE_SEA"}],
        dry_run=False,
    )
    assert r["aplicados"] == []
    assert r["omitidos"][0]["razon"] == "estado elegido invalido"
    assert (tmp_path / "32_PLAN_VOCAB.md").read_text(encoding="utf-8") == body


# ── Caso 23 (v3/ADICIÓN 4 centinela sobre el corpus VIVO) ────────────────────

def test_case23_centinela_corpus_vivo_alta_tiene_marcador():
    docs_dir = plans_board.docs_dir_default()
    if not docs_dir.exists():
        pytest.skip("docs/ no existe en este deploy (congelado)")
    preview = preview_estado_migration(docs_dir)
    for p in preview["propuestas"]:
        if p["confianza"] == "alta":
            assert any(
                "Registro de implementaci" in e or "ledger.json" in e for e in p["evidencia"]
            ), p


# ── Caso 24 (v3/ADICIÓN 4 ninguna propuesta miente por default) ─────────────

def test_case24_ninguna_propuesta_miente_por_default():
    docs_dir = plans_board.docs_dir_default()
    if not docs_dir.exists():
        pytest.skip("docs/ no existe en este deploy (congelado)")
    preview = preview_estado_migration(docs_dir)
    assert preview["por_confianza"].get("sin_evidencia", 0) == sum(
        1 for p in preview["propuestas"] if not p["aplicable"]
    )
    for p in preview["propuestas"]:
        if not p["aplicable"]:
            assert p["estado_propuesto"] is None


# ── Caso 25 (v4/C2 la Regla 1 importa, no reescribe) ─────────────────────────

def test_case25_ledger_ok_veredictos_es_el_mismo_objeto():
    assert pem._LEDGER_OK_VEREDICTOS is plans_board._LEDGER_OK_VEREDICTOS
