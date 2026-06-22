#!/usr/bin/env python3
"""Tests del modo AOTL (AI-driven) de Kaizen. stdlib pura, sin red, sin contaminar sesiones.

Corre con el intérprete del repo:
    python scripts/test_aotl.py        # exit 0 si todo verde

Cubre las invariantes que sostienen la seguridad del loop:
  - guardarraíl de rutas (sólo kaizen/, nunca datos/maquinaria),
  - validación + apply/rollback determinista y reversible (en dir temporal),
  - contratos del motor mock (proposal/evaluation válidas),
  - extracción de JSON de la salida del modelo,
  - gate determinista en sus 4 caminos (accept / reject / escalado x2).
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import aotl_state as st          # noqa: E402
import apply as ap               # noqa: E402
import engine as eng             # noqa: E402
import run_session as rs         # noqa: E402
import dashboard as dash         # noqa: E402
from _config import load_yaml    # noqa: E402

CONTRACTS = ROOT / "contracts"
_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str):
    def deco(fn):
        try:
            fn()
            _RESULTS.append((name, True, ""))
        except AssertionError as exc:
            _RESULTS.append((name, False, str(exc) or "assert"))
        except Exception as exc:  # noqa: BLE001
            _RESULTS.append((name, False, "%s: %s" % (type(exc).__name__, exc)))
        return fn
    return deco


def required_of(schema_file: str) -> list[str]:
    return json.loads((CONTRACTS / schema_file).read_text(encoding="utf-8")).get("required", [])


class DummyFx:
    """Forense de juguete: no escribe nada (evita tocar el log global real)."""
    def info(self, *a, **k): return None
    def warn(self, *a, **k): return None
    def error(self, *a, **k): return None


# --- guardarraíl de rutas -------------------------------------------------------------------
@check("guardarrail: ruta válida pasa")
def _():
    p = st.safe_target_path("playground/JOURNAL.md")
    assert p.name == "JOURNAL.md"

@check("guardarrail: '..' escapa -> rechaza")
def _():
    try:
        st.safe_target_path("../secrets.txt"); assert False, "debió rechazar"
    except ValueError:
        pass

@check("guardarrail: sessions/ protegido -> rechaza")
def _():
    try:
        st.safe_target_path("sessions/x/proposal.json"); assert False, "debió rechazar"
    except ValueError:
        pass

@check("guardarrail: maquinaria del loop protegida -> rechaza")
def _():
    # Itera TODOS los PROTECTED_FILES para que el test no quede desincronizado
    # si se agregan nuevas entradas a la tupla (ver B-21).
    for prot in st.PROTECTED_FILES:
        try:
            st.safe_target_path(prot); assert False, "debio rechazar %s" % prot
        except ValueError:
            pass

@check("is_protected: prefijo sessions/ -> True")
def _():
    assert st.is_protected("sessions/2026-01-01/proposal.json"), "sessions/ debe ser protegido"
    assert st.is_protected("sessions"), "sessions sola debe ser protegida"

@check("is_protected: archivo en PROTECTED_FILES -> True")
def _():
    # kaizen.py y scripts/run_session.py estan en PROTECTED_FILES
    assert st.is_protected("kaizen.py"), "kaizen.py debe ser protegido"
    assert st.is_protected("scripts/run_session.py"), "scripts/run_session.py debe ser protegido"

@check("is_protected: extra_protected funciona")
def _():
    assert st.is_protected("scripts/custom_danger.py", extra_protected=("scripts/custom_danger.py",))
    assert not st.is_protected("scripts/custom_danger.py"), "sin extra no debe ser protegido"

@check("is_protected: ruta editable -> False")
def _():
    # scripts/test_core.py y playground/ son editables por el loop
    assert not st.is_protected("scripts/test_core.py"), "test_core debe ser editable"
    assert not st.is_protected("playground/JOURNAL.md"), "playground debe ser editable"


# --- validación + apply/rollback ------------------------------------------------------------
@check("validate_change_set: bueno -> sin errores")
def _():
    cs = {"changes": [{"path": "notes.md", "action": "create", "content": "x"}]}
    tmp = Path(tempfile.mkdtemp())
    try:
        assert ap.validate_change_set(cs, root=tmp) == []
    finally:
        shutil.rmtree(tmp)

@check("validate_change_set: action mala y content faltante -> errores")
def _():
    cs = {"changes": [{"path": "a.md", "action": "frobnicate"},
                      {"path": "b.md", "action": "modify"}]}
    tmp = Path(tempfile.mkdtemp())
    try:
        errs = ap.validate_change_set(cs, root=tmp)
        assert len(errs) >= 2, errs
    finally:
        shutil.rmtree(tmp)

@check("apply+rollback: modify/create round-trip reversible")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "f.md").write_text("ORIGINAL\n", encoding="utf-8")
        cs = {"changes": [
            {"path": "f.md", "action": "modify", "content": "NUEVO\n"},
            {"path": "sub/new.md", "action": "create", "content": "creado\n"},
        ]}
        manifest = ap.apply_change_set("sid1", cs, root=tmp)
        assert (tmp / "f.md").read_text(encoding="utf-8") == "NUEVO\n"
        assert (tmp / "sub" / "new.md").exists()
        assert (tmp / "sessions" / "sid1" / "_apply" / "applied.json").exists()
        assert len(manifest["changes"]) == 2
        n = ap.rollback("sid1", root=tmp)
        assert (tmp / "f.md").read_text(encoding="utf-8") == "ORIGINAL\n", "modify no revirtió"
        assert not (tmp / "sub" / "new.md").exists(), "create no se borró"
        assert not (tmp / "sub").exists(), "dir creado no se limpió"
        assert n == 2, n
    finally:
        shutil.rmtree(tmp)

@check("apply: rechaza ruta fuera de root")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        cs = {"changes": [{"path": "../escape.md", "action": "create", "content": "x"}]}
        try:
            ap.apply_change_set("sid2", cs, root=tmp); assert False, "debió fallar"
        except ValueError:
            pass
        assert not (tmp.parent / "escape.md").exists()
    finally:
        shutil.rmtree(tmp)


# --- motor mock: contratos ------------------------------------------------------------------
@check("mock.propose: proposal cumple required + change_set válido")
def _():
    m = eng.MockEngine()
    proposal, cs = m.propose({"session_id": "s", "iteration": 1, "files": {}})
    for k in required_of("proposal.schema.json"):
        assert k in proposal, "falta %s" % k
    assert proposal["reversibility"]["rollback"], "rollback obligatorio"
    assert cs["changes"][0]["action"] == "modify"

@check("mock.evaluate: passed=True -> accept; passed=False -> reject+bloqueante")
def _():
    m = eng.MockEngine()
    ok = m.evaluate({}, {"passed": True}, {"session_id": "s"})
    bad = m.evaluate({}, {"passed": False, "summary": "boom"}, {"session_id": "s"})
    for ev in (ok, bad):
        for k in required_of("evaluation.schema.json"):
            assert k in ev, "falta %s" % k
        assert ev["total"] == sum(ev["scores"].values()), "total != suma"
    assert ok["preliminary_verdict"] == "accept" and ok["confidence"] >= 0.7
    assert bad["preliminary_verdict"] == "reject" and bad["blocking"]


# --- extracción de JSON del modelo ----------------------------------------------------------
@check("extract_json: fenced / raw / con prosa / inválido")
def _():
    assert eng.extract_json('```json\n{"a":1}\n```')["a"] == 1
    assert eng.extract_json('{"b":2}')["b"] == 2
    assert eng.extract_json('texto ```json\n{"c":3}\n``` mas texto')["c"] == 3
    try:
        eng.extract_json("sin json aqui"); assert False, "debió fallar"
    except eng.EngineError:
        pass

@check("parse_file_blocks: extrae contenido (con comillas/comas) fuera del JSON")
def _():
    text = ('```json\n{"change_set":{"changes":[{"path":"a.md","action":"modify"}]}}\n```\n'
            '===KAIZEN-FILE: a.md===\nlinea1\n"comillas", comas y { llaves }\n===KAIZEN-END===')
    blocks = eng.parse_file_blocks(text)
    assert blocks["a.md"] == 'linea1\n"comillas", comas y { llaves }', repr(blocks)


# --- gate determinista (los 4 caminos) ------------------------------------------------------
def _profile():
    return load_yaml(ROOT / "config" / "profiles" / "default.yaml")

def _decide(scores_total, conf, reversible, blocking):
    proposal = {"session_id": "s",
                "reversibility": {"reversible": reversible, "rollback": "x" if reversible else ""}}
    evaluation = {"scores": {"value": scores_total, "correctness": 0, "scope": 0,
                             "reversibility": 0, "measurability": 0},
                  "total": scores_total, "blocking": blocking, "confidence": conf}
    return rs.gate_decide(proposal, evaluation, _profile(), DummyFx())

@check("gate: alto score + alta confianza + reversible -> accept")
def _():
    d = _decide(14, 0.9, True, [])
    assert d["verdict"] == "accept" and not d["escalated_to_human"], d

@check("gate: baja confianza -> iterate + escalado")
def _():
    d = _decide(14, 0.5, True, [])
    assert d["verdict"] == "iterate" and d["escalated_to_human"], d

@check("gate: irreversible -> iterate + escalado")
def _():
    d = _decide(14, 0.9, False, [])
    assert d["verdict"] == "iterate" and d["escalated_to_human"], d

@check("gate: score bajo -> reject")
def _():
    d = _decide(5, 0.9, True, [])
    assert d["verdict"] == "reject", d

@check("gate: score zona iterate (8) sin bloqueantes -> iterate sin escalar")
def _():
    # iterate_floor=7, accept_threshold=11 en default.yaml
    d = _decide(8, 0.9, True, [])
    assert d["verdict"] == "iterate", d
    # score en zona iterate sin baja confianza: NO escala al humano
    assert not d["escalated_to_human"], "zona iterate por score no debe escalar al humano"

@check("gate: bloqueante B1 + score alto -> iterate (no accept) con blocking_details")
def _():
    # block_on_any_blocking=True en default.yaml: el bloqueante veta accept
    d = _decide(14, 0.9, True, ["B1"])
    assert d["verdict"] in ("iterate", "reject"), d
    assert "B1" in d.get("blocking_details", [""])[0], "debe describir B1 en blocking_details"

@check("gate: bloqueante B2 + score bajo -> reject (no iterate)")
def _():
    # score < iterate_floor (7) con bloqueante: resultado es reject
    d = _decide(4, 0.9, True, ["B2"])
    assert d["verdict"] == "reject", "score < floor con bloqueante debe dar reject, got %s" % d["verdict"]


# --- dashboard: estado agregado no rompe ----------------------------------------------------
@check("dashboard.build_state: estructura esperada")
def _():
    state = dash.build_state()
    assert set(("loop", "metrics", "sessions")) <= set(state.keys())
    assert "by_impl" in state["metrics"]


def main() -> int:
    for fn in list(globals().values()):
        pass  # los checks ya corrieron al definirse (decorador)
    ok = sum(1 for _, p, _ in _RESULTS if p)
    for name, passed, detail in _RESULTS:
        print("%s  %s%s" % ("OK  " if passed else "FAIL", name, "" if passed else "  -> " + detail))
    print("\n%d/%d verdes." % (ok, len(_RESULTS)))
    return 0 if ok == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
