#!/usr/bin/env python3
"""Arnés de ejecución de una sesión Kaizen con gate determinista y log forense.

Actúa como el "motor" del modo AOTL: dada una sesión que ya tiene proposal.json y
evaluation.json, valida los artefactos contra los contratos (chequeo de campos requeridos,
stdlib puro), aplica el gate de config/profiles/<profile>.yaml, escribe decision.json y
session.output.json, actualiza el índice, y deja traza forense completa.

No ejecuta cambios sobre ningún proyecto: solo decide y registra (ver ASSUMPTIONS L1).
Uso:
    python scripts/run_session.py <session_id>
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _config import load_yaml          # noqa: E402
from forensic import Forensic, sha256_file  # noqa: E402

SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"
CONTRACTS = ROOT / "contracts"
CONFIG = ROOT / "config" / "kaizen.config.yaml"


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def required_keys(schema: dict) -> list[str]:
    return list(schema.get("required", []))


def validate_required(obj: dict, schema_path: Path) -> list[str]:
    """Validación mínima portable: campos requeridos de primer nivel presentes.
    Devuelve lista de faltantes (vacía = OK). No depende de jsonschema."""
    schema = load_json(schema_path)
    missing = [k for k in required_keys(schema) if k not in obj]
    return missing


def load_profile() -> dict:
    profile_name = "default"
    if CONFIG.exists():
        cfg = load_yaml(CONFIG)
        profile_name = cfg.get("profile", "default")
    return load_yaml(ROOT / "config" / "profiles" / ("%s.yaml" % profile_name))


def compute_total(scores: dict) -> int:
    return sum(int(scores.get(k, 0)) for k in
               ("value", "correctness", "scope", "reversibility", "measurability"))


def gate_decide(proposal: dict, evaluation: dict, profile: dict, fx: Forensic) -> dict:
    """Aplica la política y devuelve un dict de decisión (contracts/decision.schema.json)."""
    review = profile.get("review", {})
    aotl = profile.get("aotl", {})
    accept_threshold = int(review.get("accept_threshold", 11))
    iterate_floor = int(review.get("iterate_floor", 7))
    min_confidence = float(review.get("min_confidence", 0.7))
    require_reversibility = bool(aotl.get("require_reversibility", True))
    block_on_any_blocking = bool(aotl.get("block_on_any_blocking", True))

    total = compute_total(evaluation.get("scores", {}))
    reported = evaluation.get("total")
    if reported is not None and int(reported) != total:
        fx.warn("gate.total_mismatch", phase="decide",
                reported=reported, computed=total)

    blocking = evaluation.get("blocking", []) or []
    confidence = float(evaluation.get("confidence", 1))
    reversible = bool(proposal.get("reversibility", {}).get("reversible", False))
    rollback = (proposal.get("reversibility", {}).get("rollback") or "").strip()

    reasons: list[str] = []
    escalate = False
    verdict = "reject"

    # Descripciones canónicas de cada código de bloqueante (docs/04_HUMAN_REVIEW.md)
    _BLOCKING_DESCRIPTIONS = {
        "B1": "B1: propuesta sin rollback declarado (reversibilidad faltante)",
        "B2": "B2: acción destructiva o irreversible sin aprobación humana explícita",
        "B3": "B3: scope creep — la sesión supera su alcance declarado",
        "B4": "B4: métrica de éxito no verificable objetivamente",
    }
    blocking_details = [_BLOCKING_DESCRIPTIONS.get(b, b) for b in blocking]

    # 1) Bloqueantes vetan accept.
    if blocking and block_on_any_blocking:
        reasons.append("bloqueantes disparados: %s" % ", ".join(blocking))
        verdict = "iterate" if total >= iterate_floor else "reject"
    # 2) Reversibilidad obligatoria.
    elif require_reversibility and not (reversible or rollback):
        reasons.append("propuesta sin reversibilidad ni rollback")
        escalate = True
        verdict = "iterate"
    # 3) Confianza baja => escalar a humano.
    elif confidence < min_confidence:
        reasons.append("confianza %.2f < umbral %.2f" % (confidence, min_confidence))
        escalate = True
        verdict = "iterate"
    # 4) Score.
    elif total >= accept_threshold:
        reasons.append("score %d >= umbral %d, sin bloqueantes" % (total, accept_threshold))
        verdict = "accept"
    elif total >= iterate_floor:
        reasons.append("score %d en zona de iteración [%d, %d)" %
                       (total, iterate_floor, accept_threshold))
        verdict = "iterate"
    else:
        reasons.append("score %d <= piso %d" % (total, iterate_floor - 1))
        verdict = "reject"

    fx.info("gate.evaluate", phase="decide", total=total, blocking=blocking,
            confidence=confidence, reversible=reversible, verdict=verdict,
            escalate_to_human=escalate, accept_threshold=accept_threshold)

    decision: dict = {
        "session_id": proposal.get("session_id"),
        "verdict": verdict,
        "rationale": "; ".join(reasons),
        "decided_by": "gate",
        "escalated_to_human": escalate,
        "decided_utc": utc_now(),
        "next_steps": [],
        "child_session": None,
        "promoted_artifacts": [],
        "_meta": {"computed_total": total},
    }
    if blocking_details:
        decision["blocking_details"] = blocking_details
    return decision


def update_index_status(session_id: str, status: str, verdict: str) -> None:
    data = load_json(INDEX)
    for entry in data.get("sessions", []):
        if entry.get("id") == session_id:
            entry["status"] = status
            entry["verdict"] = verdict
    INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    positional = [a for a in argv if not a.startswith("--")]
    if not positional:
        print("uso: python scripts/run_session.py <session_id> [--json]", file=sys.stderr)
        return 2
    session_id = positional[0]
    session_dir = SESSIONS / session_id
    if not session_dir.is_dir():
        print("ERROR: no existe la sesión %s" % session_id, file=sys.stderr)
        return 1

    fx = Forensic(session_id, session_dir, run_kind="run_session")
    fx.info("run.start", phase="run", session_dir=session_dir.relative_to(ROOT).as_posix())

    # Cargar artefactos
    inputs = {
        "session.input": (session_dir / "session.json", "session.input.schema.json"),
        "proposal": (session_dir / "proposal.json", "proposal.schema.json"),
        "evaluation": (session_dir / "evaluation.json", "evaluation.schema.json"),
    }
    loaded: dict[str, dict] = {}
    for name, (path, schema) in inputs.items():
        if not path.exists():
            fx.error("load.missing", phase="observe", artifact=name,
                     path=path.relative_to(ROOT).as_posix())
            print("ERROR: falta %s (%s)" % (name, path), file=sys.stderr)
            return 1
        obj = load_json(path)
        missing = validate_required(obj, CONTRACTS / schema)
        digest = sha256_file(path)
        if missing:
            fx.error("validate.failed", phase="observe", artifact=name,
                     missing=missing, sha256=digest)
            print("ERROR: %s no cumple el contrato; faltan %s" % (name, missing), file=sys.stderr)
            return 1
        fx.info("validate.ok", phase="observe", artifact=name, sha256=digest)
        loaded[name] = obj

    proposal = loaded["proposal"]
    evaluation = loaded["evaluation"]

    # Gate determinista
    profile = load_profile()
    decision = gate_decide(proposal, evaluation, profile, fx)

    # Escribir decision.json (mirror humano: decision.md ya existe del template)
    decision_path = session_dir / "decision.json"
    decision_path.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    fx.info("decision.written", phase="decide", verdict=decision["verdict"],
            escalated=decision["escalated_to_human"], sha256=sha256_file(decision_path))

    # Espejo humano legible de la decisión (decision.md) — coincide con el JSON.
    decision_md = (
        "# Decisión — %s\n\n"
        "- **Veredicto:** %s\n"
        "- **Decidido por:** %s\n"
        "- **Escalado a humano:** %s\n"
        "- **Fecha (UTC):** %s\n"
        "- **Score total:** %d\n\n"
        "## Justificación\n%s\n"
    ) % (
        session_id, decision["verdict"], decision["decided_by"],
        str(decision["escalated_to_human"]).lower(), decision["decided_utc"],
        decision["_meta"]["computed_total"], decision["rationale"],
    )
    (session_dir / "decision.md").write_text(decision_md, encoding="utf-8")
    fx.info("decision.md.written", phase="decide")

    # session.output.json
    status = "closed" if decision["verdict"] in ("accept", "reject") else "decided"
    output = {
        "input": loaded["session.input"],
        "proposal": proposal,
        "evaluation": evaluation,
        "decision": {k: v for k, v in decision.items() if k != "_meta"},
        "artifacts": [],
        "closed_utc": utc_now(),
    }
    out_path = session_dir / "session.output.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    fx.info("output.written", phase="register", sha256=sha256_file(out_path), status=status)

    update_index_status(session_id, status, decision["verdict"])
    fx.info("index.updated", phase="register", status=status, verdict=decision["verdict"])
    fx.info("run.end", phase="run", verdict=decision["verdict"],
            total=decision["_meta"]["computed_total"], status=status)

    if as_json:
        print(json.dumps({
            "session_id": session_id,
            "verdict": decision["verdict"],
            "status": status,
            "total": decision["_meta"]["computed_total"],
            "escalated_to_human": decision["escalated_to_human"],
        }, ensure_ascii=False))
    else:
        print("verdict=%s status=%s total=%d escalated=%s" % (
            decision["verdict"], status, decision["_meta"]["computed_total"],
            decision["escalated_to_human"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
