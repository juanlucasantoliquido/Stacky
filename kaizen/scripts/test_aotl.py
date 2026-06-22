#!/usr/bin/env python3
"""Tests del modo AOTL (AI-driven) de Kaizen. stdlib pura, sin red, sin contaminar sesiones. (58 tests)

Corre con el intérprete del repo:
    python scripts/test_aotl.py        # exit 0 si todo verde

Cubre las invariantes que sostienen la seguridad del loop:
  - guardarraíl de rutas (sólo kaizen/, nunca datos/maquinaria),
  - validación + apply/rollback determinista y reversible (en dir temporal),
  - contratos del motor mock (proposal/evaluation válidas),
  - extracción de JSON de la salida del modelo (extract_json, parse_file_blocks),
  - normalize_proposal: session_id forzado, defaults risks/artifacts, author respetado,
  - normalize_evaluation: total derivado de scores, defaults findings/blocking,
  - gate determinista en sus 4 caminos (accept / reject / escalado x2),
  - promote_decision: next_adr_number + already_promoted (idempotencia),
  - set_impl_status + update_index_fields (trazabilidad del loop),
  - spawn_child: caminos de error (no_args, no_decision, non_iterate) + idempotencia,
  - forensic.py: sha256_text, sha256_file, Forensic.log() campos + seq monotonica,
  - aotl_state.py: write/read/clear loop_status, request/stop/clear_stop (6 tests),
  - engine.py: make_engine — factory devuelve MockEngine por defecto y con driver='mock',
  - engine.py: ClaudeCliEngine._context_block — encabezado+rutas prohibidas, tree+decisions incluidos.
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
import promote_decision as pd    # noqa: E402
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


@check("applied_paths: sin manifest devuelve lista vacia")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        paths = ap.applied_paths("sid_no_existe", root=tmp)
        assert paths == [], "sin manifest debe ser lista vacia: %r" % paths
    finally:
        shutil.rmtree(tmp)


@check("applied_paths: tras apply devuelve rutas aplicadas")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "f.md").write_text("ORIGINAL\n", encoding="utf-8")
        cs = {"changes": [
            {"path": "f.md", "action": "modify", "content": "NUEVO\n"},
            {"path": "g.md", "action": "create", "content": "creado\n"},
        ]}
        ap.apply_change_set("sid_ap", cs, root=tmp)
        paths = ap.applied_paths("sid_ap", root=tmp)
        assert len(paths) == 2, "debe haber 2 rutas: %r" % paths
        assert "f.md" in paths and "g.md" in paths, "rutas incorrectas: %r" % paths
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
@check("extract_json: fenced / raw / con prosa / fence-sin-json / vacio / invalido")
def _():
    assert eng.extract_json('```json\n{"a":1}\n```')["a"] == 1
    assert eng.extract_json('{"b":2}')["b"] == 2
    assert eng.extract_json('texto ```json\n{"c":3}\n``` mas texto')["c"] == 3
    # fence sin prefijo "json" — rama elif '```' in text (caso real de algunos modelos)
    assert eng.extract_json('```\n{"d":4}\n```')["d"] == 4, "fence sin 'json' debe parsear"
    # entrada vacia o solo espacios -> EngineError
    try:
        eng.extract_json("   "); assert False, "espacios vacios debio fallar"
    except eng.EngineError:
        pass
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


@check("normalize_proposal: fuerza session_id, setdefaults risks/artifacts, no pisa author dado")
def _():
    p = eng.normalize_proposal({"title": "t", "author": "human"}, "s-123", "agent:mock")
    assert p["session_id"] == "s-123", "session_id debe sobrescribirse"
    assert p["author"] == "human", "author dado no debe pisarse"
    assert p["risks"] == [], "risks debe defaultear a []"
    assert p["artifacts"] == [], "artifacts debe defaultear a []"


@check("normalize_proposal: sin author -> usa el default del parametro")
def _():
    p = eng.normalize_proposal({"title": "t"}, "s-456", "agent:improver")
    assert p["author"] == "agent:improver", "author debe tomarse del parametro"


@check("normalize_evaluation: computa total desde scores y setdefaults findings/blocking")
def _():
    e = eng.normalize_evaluation(
        {"scores": {"value": 3, "correctness": 2, "scope": 3,
                    "reversibility": 3, "measurability": 2}},
        "s-789", "agent:evaluator"
    )
    assert e["session_id"] == "s-789", "session_id debe sobrescribirse"
    assert e["total"] == 13, "total debe sumar scores: got %d" % e.get("total", -1)
    assert e["findings"] == [], "findings debe defaultear a []"
    assert e["blocking"] == [], "blocking debe defaultear a []"


@check("normalize_evaluation: sin scores no pone total")
def _():
    e = eng.normalize_evaluation({}, "s-000", "agent:eval")
    assert "total" not in e, "sin scores no debe haber total"


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


# --- set_impl_status y update_index_fields -------------------------------------------------
def _make_tmp_index(session_id: str, extra: dict | None = None) -> Path:
    """Crea un indice temporal con una sesion de prueba y devuelve su path."""
    tmp = Path(tempfile.mkdtemp())
    entry: dict = {"id": session_id, "status": "closed", "verdict": "accept"}
    if extra:
        entry.update(extra)
    idx_path = tmp / "sessions" / "_index.json"
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(
        json.dumps({"sessions": [entry]}), encoding="utf-8"
    )
    return idx_path


@check("set_impl_status: escribe impl_status + auto=True en el indice")
def _():
    tmp_idx = _make_tmp_index("s-impl-1")
    try:
        st.set_impl_status("s-impl-1", "implemented", index=tmp_idx)
        data = json.loads(tmp_idx.read_text(encoding="utf-8"))
        entry = data["sessions"][0]
        assert entry.get("impl_status") == "implemented", entry
        assert entry.get("auto") is True, "debe agregar auto=True"
    finally:
        shutil.rmtree(tmp_idx.parent.parent)

@check("set_impl_status: rechaza impl_status invalido")
def _():
    tmp_idx = _make_tmp_index("s-impl-2")
    try:
        try:
            st.set_impl_status("s-impl-2", "invalid_status", index=tmp_idx)
            assert False, "debio rechazar"
        except ValueError:
            pass
    finally:
        shutil.rmtree(tmp_idx.parent.parent)

@check("update_index_fields: merge sin borrar campos previos")
def _():
    tmp_idx = _make_tmp_index("s-merge-1", extra={"tag": "prev_tag"})
    try:
        st.update_index_fields("s-merge-1", {"new_field": "new_val"}, index=tmp_idx)
        data = json.loads(tmp_idx.read_text(encoding="utf-8"))
        entry = data["sessions"][0]
        assert entry.get("tag") == "prev_tag", "no debe borrar campos previos"
        assert entry.get("new_field") == "new_val", "debe agregar el nuevo campo"
    finally:
        shutil.rmtree(tmp_idx.parent.parent)


# --- promote_decision: numeracion y idempotencia --------------------------------------------
@check("promote: next_adr_number con decisions/ vacio -> 1")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp).mkdir(exist_ok=True)
        orig = pd.DECISIONS; pd.DECISIONS = tmp
        try:
            assert pd.next_adr_number() == 1, "debe devolver 1 si no hay ADRs"
        finally:
            pd.DECISIONS = orig
    finally:
        shutil.rmtree(tmp)

@check("promote: next_adr_number con 3 ADRs -> 4")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        for n in (1, 2, 3):
            fname = "%04d-adr-%d.md" % (n, n)
            (tmp / fname).write_text("# ADR %04d\n" % n, encoding="utf-8")
        orig = pd.DECISIONS; pd.DECISIONS = tmp
        try:
            assert pd.next_adr_number() == 4, "debe devolver 4 si el maximo es 3"
        finally:
            pd.DECISIONS = orig
    finally:
        shutil.rmtree(tmp)

@check("promote: already_promoted devuelve None y Path correctamente")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        orig = pd.DECISIONS; pd.DECISIONS = tmp
        try:
            assert pd.already_promoted("s-no-existe") is None, "debe devolver None si no hay marker"
            adr = tmp / "0001-test.md"
            adr.write_text("# ADR 0001\n- session: s-existe\n", encoding="utf-8")
            result = pd.already_promoted("s-existe")
            assert result is not None, "debe devolver Path cuando hay marker"
            assert result.name == "0001-test.md", "debe devolver el path correcto"
        finally:
            pd.DECISIONS = orig
    finally:
        shutil.rmtree(tmp)


# --- spawn_child: caminos de error e idempotencia ------------------------------------------
import spawn_child as sc  # noqa: E402


def _mk_decision(tmp: Path, session_id: str, verdict: str, child_session: "str | None" = None) -> Path:
    """Crea estructura minima de sesion madre con decision.json en tempdir."""
    d = tmp / "sessions" / session_id
    d.mkdir(parents=True, exist_ok=True)
    decision: dict = {"session_id": session_id, "verdict": verdict, "next_steps": []}
    if child_session:
        decision["child_session"] = child_session
    (d / "decision.json").write_text(json.dumps(decision), encoding="utf-8")
    session: dict = {"id": session_id, "objective": "test obj", "parent_session": None}
    (d / "session.json").write_text(json.dumps(session), encoding="utf-8")
    return d


@check("spawn_child: sin args -> exit 2")
def _():
    orig_sessions = sc.SESSIONS
    try:
        assert sc.main([]) == 2, "sin args debe devolver exit 2"
    finally:
        sc.SESSIONS = orig_sessions


@check("spawn_child: sesion sin decision.json -> exit 1")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        # Crear directorio de sesion sin decision.json
        sid = "s-nodecision"
        (tmp / "sessions" / sid).mkdir(parents=True)
        orig = sc.SESSIONS; sc.SESSIONS = tmp / "sessions"
        try:
            assert sc.main([sid]) == 1, "sin decision.json debe devolver exit 1"
        finally:
            sc.SESSIONS = orig
    finally:
        shutil.rmtree(tmp)


@check("spawn_child: verdict != iterate -> exit 1")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        sid = "s-accept"
        _mk_decision(tmp, sid, verdict="accept")
        orig = sc.SESSIONS; sc.SESSIONS = tmp / "sessions"
        try:
            assert sc.main([sid]) == 1, "verdict=accept debe rechazar (solo itera en 'iterate')"
        finally:
            sc.SESSIONS = orig
    finally:
        shutil.rmtree(tmp)


@check("spawn_child: idempotente si ya tiene child_session")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        sid = "s-idem"
        _mk_decision(tmp, sid, verdict="iterate", child_session="child-ya-existente")
        orig = sc.SESSIONS; sc.SESSIONS = tmp / "sessions"
        try:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sc.main([sid])
            assert rc == 0, "idempotente debe devolver exit 0, got %d" % rc
            assert "child-ya-existente" in buf.getvalue(), "debe imprimir el child_id existente"
        finally:
            sc.SESSIONS = orig
    finally:
        shutil.rmtree(tmp)


# --- forensic: sha256 + Forensic.log() con GLOBAL_LOG parchado ----------------------------
import forensic as fx  # noqa: E402


@check("forensic.sha256_text: determinista y 64 hex chars")
def _():
    h1 = fx.sha256_text("hola")
    h2 = fx.sha256_text("hola")
    assert h1 == h2, "debe ser determinista"
    assert len(h1) == 64, "sha256 debe tener 64 hex chars"
    assert h1 != fx.sha256_text("otra"), "hashes distintos para inputs distintos"


@check("forensic.sha256_file: None si no existe, hex si existe")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        assert fx.sha256_file(tmp / "noexiste.txt") is None, "debe devolver None si no existe"
        f = tmp / "real.txt"
        f.write_text("contenido", encoding="utf-8")
        h = fx.sha256_file(f)
        assert h is not None and len(h) == 64, "debe devolver 64 hex chars para archivo existente"
    finally:
        shutil.rmtree(tmp)


@check("forensic.Forensic.log: escribe JSONL con campos requeridos")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        sid = "s-ftest"
        sdir = tmp / "sessions" / sid
        sdir.mkdir(parents=True)
        # Parchamos GLOBAL_LOG para no contaminar el log real
        orig_gl = fx.GLOBAL_LOG; fx.GLOBAL_LOG = tmp / "sessions" / "_forensic.jsonl"
        try:
            f = fx.Forensic(sid, sdir, run_kind="run_session")
            rec = f.info("test.event", phase="gate", score=42)
            # Verificar campos en el dict devuelto
            for k in ("ts", "seq", "run_id", "run_kind", "session_id", "phase", "event", "level", "elapsed_ms"):
                assert k in rec, "falta campo %s en el record" % k
            assert rec["event"] == "test.event"
            assert rec["level"] == "INFO"
            assert rec["data"].get("score") == 42
            # Verificar que se escribio en el JSONL de sesion
            lines = (sdir / "forensic.jsonl").read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1, "debe haber 1 linea JSONL"
            parsed = json.loads(lines[0])
            assert parsed["event"] == "test.event"
        finally:
            fx.GLOBAL_LOG = orig_gl
    finally:
        shutil.rmtree(tmp)


@check("forensic.Forensic.log: seq monotonica y elapsed_ms no negativo")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        sid = "s-seq"
        sdir = tmp / "sessions" / sid
        sdir.mkdir(parents=True)
        orig_gl = fx.GLOBAL_LOG; fx.GLOBAL_LOG = tmp / "_g.jsonl"
        try:
            f = fx.Forensic(sid, sdir)
            r1 = f.info("e1")
            r2 = f.warn("e2")
            r3 = f.error("e3")
            assert r1["seq"] < r2["seq"] < r3["seq"], "seq debe ser monotonica"
            assert r1["elapsed_ms"] >= 0 and r2["elapsed_ms"] >= 0, "elapsed_ms no negativo"
            assert r2["level"] == "WARN" and r3["level"] == "ERROR"
        finally:
            fx.GLOBAL_LOG = orig_gl
    finally:
        shutil.rmtree(tmp)


# --- aotl_state: loop_status (write/read/clear) + stop flag (request/stop/clear) -----------
import aotl_state as _ast  # noqa: E402


@check("aotl_state.write_loop_status: agrega updated_utc y el campo dado")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "_loop.status.json"
        _ast.write_loop_status({"phase": "propose", "iteration": 1}, path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["phase"] == "propose", "debe preservar el campo dado"
        assert "updated_utc" in data, "debe agregar updated_utc"
    finally:
        shutil.rmtree(tmp)


@check("aotl_state.read_loop_status: devuelve None si no existe")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        result = _ast.read_loop_status(path=tmp / "_no_existe.json")
        assert result is None, "debe devolver None si el archivo no existe"
    finally:
        shutil.rmtree(tmp)


@check("aotl_state.read_loop_status: devuelve dict si existe")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "_loop.status.json"
        _ast.write_loop_status({"phase": "run"}, path=path)
        result = _ast.read_loop_status(path=path)
        assert isinstance(result, dict), "debe devolver dict"
        assert result["phase"] == "run"
    finally:
        shutil.rmtree(tmp)


@check("aotl_state.clear_loop_status: borra el archivo existente")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "_loop.status.json"
        path.write_text("{}", encoding="utf-8")
        _ast.clear_loop_status(path=path)
        assert not path.exists(), "clear debe eliminar el archivo"
    finally:
        shutil.rmtree(tmp)


@check("aotl_state.request_stop + stop_requested: crea y detecta el flag")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        flag = tmp / "_loop.stop"
        assert not _ast.stop_requested(path=flag), "no debe haber flag inicial"
        _ast.request_stop(path=flag, reason="test")
        assert _ast.stop_requested(path=flag), "despues de request_stop debe existir el flag"
        data = json.loads(flag.read_text(encoding="utf-8"))
        assert data["reason"] == "test", "debe persistir el reason"
    finally:
        shutil.rmtree(tmp)


@check("aotl_state.clear_stop: elimina el flag de parada")
def _():
    tmp = Path(tempfile.mkdtemp())
    try:
        flag = tmp / "_loop.stop"
        _ast.request_stop(path=flag)
        assert _ast.stop_requested(path=flag)
        _ast.clear_stop(path=flag)
        assert not _ast.stop_requested(path=flag), "tras clear_stop no debe existir el flag"
    finally:
        shutil.rmtree(tmp)


# --- dashboard: estado agregado no rompe ----------------------------------------------------
@check("dashboard.build_state: estructura esperada")
def _():
    state = dash.build_state()
    assert set(("loop", "metrics", "sessions")) <= set(state.keys())
    assert "by_impl" in state["metrics"]


# --- engine.py: make_engine factory -----------------------------------------------------------
import engine as _eng  # noqa: E402


@check("make_engine: sin config devuelve MockEngine")
def _():
    eng = _eng.make_engine({})
    assert isinstance(eng, _eng.MockEngine), "debe devolver MockEngine sin config"


@check("make_engine: con driver='mock' explicito devuelve MockEngine")
def _():
    eng = _eng.make_engine({"engine": {"driver": "mock"}})
    assert isinstance(eng, _eng.MockEngine), "debe devolver MockEngine con driver=mock"


@check("ClaudeCliEngine._context_block: contexto vacio tiene encabezado y rutas prohibidas")
def _():
    result = eng.ClaudeCliEngine._context_block({"objective": "obj", "protected": ["kaizen.py"]})
    assert "## Contexto observado" in result, "debe tener encabezado"
    assert "obj" in result, "debe incluir el objetivo"
    assert "kaizen.py" in result, "debe incluir rutas protegidas"

@check("ClaudeCliEngine._context_block: con tree y decisions incluye esas secciones")
def _():
    ctx = {
        "objective": "mejorar",
        "tree": ["scripts/metrics.py"],
        "recent_decisions": ["0001: mi-decision accept"],
        "files": {},
        "protected": [],
    }
    result = eng.ClaudeCliEngine._context_block(ctx)
    assert "### Archivos editables" in result, "debe incluir seccion de archivos"
    assert "scripts/metrics.py" in result, "debe listar el archivo del foco"
    assert "### Decisiones recientes" in result, "debe incluir seccion de decisiones"
    assert "mi-decision" in result, "debe listar la decision reciente"


# --- autoloop: create_session y run_gate con mock de _py (B-84) --------------------------------
import autoloop as _al  # noqa: E402
import subprocess as _sp  # noqa: E402


def _fake_proc(stdout: str, returncode: int = 0) -> _sp.CompletedProcess:
    return _sp.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


@check("autoloop.create_session: ok -> devuelve nombre del directorio de sesion")
def _():
    old_py = _al._py
    try:
        _al._py = lambda *a, **kw: _fake_proc("sessions/2026-06-22T000000Z__mi-sesion-b84\n")
        sid = _al.create_session("mi objetivo", "generic", "mock")
        assert sid == "2026-06-22T000000Z__mi-sesion-b84", "debe retornar el basename de la linea de salida"
    finally:
        _al._py = old_py


@check("autoloop.create_session: returncode!=0 lanza RuntimeError")
def _():
    old_py = _al._py
    try:
        _al._py = lambda *a, **kw: _fake_proc("", returncode=1)
        raised = False
        try:
            _al.create_session("obj", "generic", "mock")
        except RuntimeError:
            raised = True
        assert raised, "debe lanzar RuntimeError si new_session falla"
    finally:
        _al._py = old_py


@check("autoloop.run_gate: ok -> devuelve dict parseado del ultimo JSON de stdout")
def _():
    old_py = _al._py
    try:
        gate_output = '{"verdict": "accept", "total": 12}\n'
        _al._py = lambda *a, **kw: _fake_proc(gate_output)
        result = _al.run_gate("alguna-sesion")
        assert result.get("verdict") == "accept", "debe parsear el veredicto"
        assert result.get("total") == 12, "debe parsear el total"
    finally:
        _al._py = old_py


@check("autoloop.run_gate: returncode!=0 lanza RuntimeError")
def _():
    old_py = _al._py
    try:
        _al._py = lambda *a, **kw: _fake_proc("error", returncode=1)
        raised = False
        try:
            _al.run_gate("alguna-sesion")
        except RuntimeError:
            raised = True
        assert raised, "debe lanzar RuntimeError si run_session falla"
    finally:
        _al._py = old_py


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
