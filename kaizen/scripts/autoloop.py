#!/usr/bin/env python3
"""Loop de automejora AOTL de Kaizen — el orquestador AI-driven. stdlib pura.

Corre el ciclo completo, vuelta tras vuelta, hasta toparse con un freno:
  observar -> PROPONER (engine) -> APLICAR (tentativo, reversible) -> MEDIR (regresión real)
  -> EVALUAR (engine) -> DECIDIR (gate determinista) -> RESOLVER.

Regla dura: SOLO lo que el gate ACEPTA se conserva (y se commitea, scopeado a kaizen/);
reject/iterate/escalate REVIERTEN el cambio tentativo. Si el gate ESCALA a humano, el loop
se DETIENE (human-in-the-loop, ver docs/06 regla 6). Frenos: flag de parada cooperativa,
tope de iteraciones, y escalado. Deja estado vivo en sessions/_loop.status.json para el dashboard.

Uso:
    python scripts/autoloop.py --engine mock --max-iterations 3 --interval 0
    python scripts/autoloop.py --engine claude --forever
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
import aotl_state as st  # noqa: E402
import apply as ap  # noqa: E402
import engine as eng  # noqa: E402
from _config import load_yaml  # noqa: E402

enable_utf8()

SCRIPTS = ROOT / "scripts"
SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"
CONFIG = ROOT / "config" / "kaizen.config.yaml"

MAX_FOCUS_FILES = 15
MAX_FOCUS_BYTES = 60_000


# --- carga de config / adapter --------------------------------------------------------------
def active_config() -> dict:
    return load_yaml(CONFIG) if CONFIG.exists() else {}


def load_adapter(name: str) -> dict:
    path = ROOT / "adapters" / name / "adapter.yaml"
    return load_yaml(path) if path.exists() else {}


def load_profile(cfg: dict) -> dict:
    profile_name = cfg.get("profile", "default")
    path = ROOT / "config" / "profiles" / ("%s.yaml" % profile_name)
    return load_yaml(path) if path.exists() else {}


# --- OBSERVAR -------------------------------------------------------------------------------
def gather_focus(focus: list[str]) -> tuple[list[str], dict]:
    """Devuelve (tree, files) del foco editable, acotado para controlar costo de contexto."""
    tree: list[str] = []
    files: dict[str, str] = {}
    budget = MAX_FOCUS_BYTES
    candidates: list[Path] = []
    for f in focus:
        p = ROOT / f
        if p.is_dir():
            candidates += sorted(q for q in p.rglob("*") if q.is_file())
        elif p.is_file():
            candidates.append(p)
    for q in candidates:
        try:
            rel = q.relative_to(ROOT).as_posix()
        except ValueError:
            continue
        if st.is_protected(rel):
            continue
        tree.append(rel)
        if len(files) >= MAX_FOCUS_FILES or budget <= 0:
            continue
        try:
            content = q.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content.encode("utf-8")) > budget:
            continue
        files[rel] = content
        budget -= len(content.encode("utf-8"))
    return tree, files


def recent_objectives(n: int = 5) -> list[str]:
    if not INDEX.exists():
        return []
    items = st.load_json(INDEX).get("sessions", [])
    return [e.get("objective", "") for e in items[-n:]]


def build_context(session_id: str, objective: str, iteration: int,
                  focus: list[str], measure_command: str) -> dict:
    tree, files = gather_focus(focus)
    return {
        "session_id": session_id,
        "objective": objective,
        "iteration": iteration,
        "root": str(ROOT),
        "tree": tree,
        "files": files,
        "recent_decisions": recent_objectives(),
        "protected": list(st.PROTECTED_PREFIXES) + list(st.PROTECTED_FILES),
        "measure_command": measure_command,
    }


# --- helpers de subprocess (reusan los scripts existentes, sin duplicar lógica) -------------
def _py(script: str, *args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          cwd=str(ROOT), capture_output=capture, text=True, encoding="utf-8")


def create_session(objective: str, adapter: str, engine_name: str) -> str:
    res = _py("new_session.py", objective, "--mode", "aotl", "--adapter", adapter,
              "--tag", "aotl", "--tag", "engine:%s" % engine_name)
    if res.returncode != 0:
        raise RuntimeError("new_session falló: %s" % res.stderr.strip())
    return Path(res.stdout.strip()).name


def measure(measure_command: str) -> dict:
    """Corre la métrica de regresión objetiva. passed = exit 0."""
    res = _py("%s.py" % measure_command)
    out = (res.stdout or "") + (res.stderr or "")
    return {"passed": res.returncode == 0, "exit": res.returncode, "summary": out.strip()[-1800:]}


def run_gate(session_id: str) -> dict:
    res = _py("run_session.py", session_id, "--json")
    if res.returncode != 0:
        raise RuntimeError("gate (run_session) falló: %s" % (res.stderr or res.stdout).strip())
    return json.loads(res.stdout.strip().splitlines()[-1])


def spawn_child(session_id: str) -> str | None:
    res = _py("spawn_child.py", session_id)
    return res.stdout.strip() if res.returncode == 0 else None


def promote(session_id: str) -> None:
    _py("promote_decision.py", session_id)


# --- una vuelta del ciclo -------------------------------------------------------------------
def run_iteration(i: int, args, adapter_cfg: dict, profile: dict, engine, totals: dict,
                  status: dict) -> str:
    """Ejecuta una vuelta. Devuelve el impl_status terminal de la sesión."""
    focus = (adapter_cfg.get("observe", {}) or {}).get("focus", ["playground"])
    measure_command = (adapter_cfg.get("measure", {}) or {}).get("command", "selfcheck")
    commit_on_accept = bool(profile.get("aotl", {}).get("commit_on_accept", True)) and not args.no_commit

    def beat(phase: str, **extra):
        status.update({"iteration": i, "phase": phase, **extra})
        st.write_loop_status(status)

    beat("observe", current_session=None)
    objective = args.objective or "automejora AOTL #%d (foco: %s)" % (i, ",".join(focus))
    sid = create_session(objective, args.adapter, engine.name)
    st.set_impl_status(sid, st.PLANNED)
    beat("propose", current_session=sid)
    print("[%d] sesión %s" % (i, sid))

    session_dir = SESSIONS / sid
    ctx = build_context(sid, objective, i, focus, measure_command)

    # PROPONER
    proposal, change_set = engine.propose(ctx)
    st.write_json(session_dir / "proposal.json", proposal)
    st.write_json(session_dir / "change_set.json", change_set)

    applied = False
    try:
        # APLICAR (tentativo, reversible)
        beat("apply", current_session=sid)
        ap.apply_change_set(sid, change_set, root=ROOT)
        applied = True
        st.set_impl_status(sid, st.APPLIED)

        # MEDIR (regresión real)
        beat("measure", current_session=sid)
        measurement = measure(measure_command)

        # EVALUAR
        beat("evaluate", current_session=sid)
        evaluation = engine.evaluate(proposal, measurement, ctx)
        st.write_json(session_dir / "evaluation.json", evaluation)

        # DECIDIR (gate determinista)
        beat("gate", current_session=sid)
        decision = run_gate(sid)
        verdict, escalated = decision["verdict"], decision.get("escalated_to_human", False)
        print("    veredicto=%s escalado=%s passed=%s" %
              (verdict, escalated, measurement["passed"]))

        # RESOLVER
        beat("resolve", current_session=sid)
        if verdict == "accept":
            applied = False  # se conserva: no revertir
            commit_info = None
            if commit_on_accept:
                ok, detail = ap.commit_applied(sid, "kaizen(auto): %s" % proposal.get("title", sid),
                                               root=ROOT)
                commit_info = detail if ok else None
            st.set_impl_status(sid, st.IMPLEMENTED, commit=commit_info)
            promote(sid)
            totals["implemented"] += 1
            return st.IMPLEMENTED
        if verdict == "iterate" and escalated:
            ap.rollback(sid, root=ROOT); applied = False
            st.set_impl_status(sid, st.ESCALATED)
            totals["escalated"] += 1
            return st.ESCALATED
        if verdict == "iterate":
            ap.rollback(sid, root=ROOT); applied = False
            child = spawn_child(sid)
            st.set_impl_status(sid, st.ITERATING, child=child)
            totals["iterating"] += 1
            return st.ITERATING
        # reject
        ap.rollback(sid, root=ROOT); applied = False
        st.set_impl_status(sid, st.REJECTED)
        totals["rejected"] += 1
        return st.REJECTED
    finally:
        if applied:  # salida anómala tras aplicar y antes de un veredicto terminal
            ap.rollback(sid, root=ROOT)
            st.set_impl_status(sid, st.REVERTED)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Loop de automejora AOTL de Kaizen.")
    parser.add_argument("--engine", choices=["mock", "claude"], default=None,
                        help="Driver del motor IA (override del adapter).")
    parser.add_argument("--adapter", default=None, help="Adapter activo (default: config o 'mock').")
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--forever", action="store_true", help="Ignora --max-iterations.")
    parser.add_argument("--interval", type=float, default=3.0, help="Segundos entre vueltas.")
    parser.add_argument("--objective", default=None, help="Objetivo semilla (opcional).")
    parser.add_argument("--no-commit", action="store_true", help="No commitear las aceptadas.")
    args = parser.parse_args(argv)

    cfg = active_config()
    # Adapter: --adapter > config.adapter > 'mock' (default seguro y offline).
    args.adapter = args.adapter or cfg.get("adapter") or "mock"
    adapter_cfg = load_adapter(args.adapter)
    profile = load_profile(cfg)
    try:
        engine = eng.make_engine(adapter_cfg, override_driver=args.engine)
    except eng.EngineError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    st.clear_stop()
    totals = {"implemented": 0, "rejected": 0, "iterating": 0, "escalated": 0}
    status = {
        "state": "running", "engine": engine.name, "adapter": args.adapter,
        "started_utc": st.utc_now(), "max_iterations": None if args.forever else args.max_iterations,
        "iteration": 0, "phase": "starting", "current_session": None, "totals": totals,
    }
    st.write_loop_status(status)
    print("== Kaizen autoloop == engine=%s adapter=%s max=%s" %
          (engine.name, args.adapter, "∞" if args.forever else args.max_iterations))

    final_state = "stopped"
    i = 0
    try:
        while True:
            i += 1
            if not args.forever and i > args.max_iterations:
                break
            if st.stop_requested():
                print("parada solicitada (flag). Cortando.")
                st.clear_stop()
                break
            try:
                terminal = run_iteration(i, args, adapter_cfg, profile, engine, totals, status)
            except eng.EngineError as exc:
                print("ERROR del motor: %s" % exc, file=sys.stderr)
                final_state = "error"
                status["last_error"] = str(exc)
                break
            if terminal == st.ESCALATED:
                print("ESCALADO a humano. El loop se detiene (human-in-the-loop).")
                final_state = "paused-escalated"
                break
            if args.interval > 0 and (args.forever or i < args.max_iterations):
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\ninterrumpido por el usuario.")
        final_state = "stopped"

    status.update({"state": final_state, "phase": "idle", "current_session": None,
                   "ended_utc": st.utc_now()})
    st.write_loop_status(status)
    print("== fin == estado=%s totales=%s" % (final_state, json.dumps(totals)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
