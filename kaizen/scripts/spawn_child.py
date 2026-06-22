#!/usr/bin/env python3
"""Crea la sesión hija de una sesión que terminó en 'iterate'. stdlib pura.

Cierra el bucle de iteración descrito en docs/03_SESSIONS.md: 'iterate' no reabre la sesión,
engendra una sesión hija que referencia a la madre en parent_session. Es idempotente: si la
decisión ya tiene child_session, no crea otra.

Uso:
    python scripts/spawn_child.py <session_id_madre>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _config import load_yaml  # noqa: E402

SESSIONS = ROOT / "sessions"
CONFIG = ROOT / "config" / "kaizen.config.yaml"


def max_iterations() -> int:
    profile_name = "default"
    if CONFIG.exists():
        profile_name = load_yaml(CONFIG).get("profile", "default")
    profile = load_yaml(ROOT / "config" / "profiles" / ("%s.yaml" % profile_name))
    return int(profile.get("aotl", {}).get("max_iterations", 3))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: python scripts/spawn_child.py <session_id_madre>", file=sys.stderr)
        return 2
    parent_id = argv[0]
    parent_dir = SESSIONS / parent_id
    decision_path = parent_dir / "decision.json"
    session_path = parent_dir / "session.json"

    if not decision_path.exists():
        print("ERROR: la sesión madre no tiene decision.json (¿corriste el gate?)", file=sys.stderr)
        return 1
    decision = load_json(decision_path)
    if decision.get("verdict") != "iterate":
        print("ERROR: la sesión no terminó en 'iterate' (verdict=%s)" % decision.get("verdict"),
              file=sys.stderr)
        return 1
    if decision.get("child_session"):
        print(decision["child_session"])  # idempotente: ya existe
        return 0

    parent_session = load_json(session_path)
    base_obj = parent_session.get("objective", parent_id)
    # Cuenta de iteración a partir de la cadena de padres (madre = iteración 1).
    iteration = 2
    cursor = parent_session
    while cursor.get("parent_session"):
        iteration += 1
        cursor = load_json(SESSIONS / cursor["parent_session"] / "session.json")

    # Salvaguarda: no encadenar iteraciones más allá del tope del perfil (evita bucles).
    cap = max_iterations()
    if iteration > cap:
        print("ERROR: tope de iteraciones alcanzado (max_iterations=%d); "
              "se requiere intervención humana." % cap, file=sys.stderr)
        return 1
    child_objective = "%s (iteracion %d)" % (base_obj, iteration)

    # Reusa new_session.py (no duplica la lógica de creación/índice).
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "new_session.py"),
         child_objective, "--parent", parent_id],
        capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR creando la hija:\n%s" % result.stderr, file=sys.stderr)
        return 1
    child_rel = result.stdout.strip()
    child_id = Path(child_rel).name

    # Enlaza la decisión y el output de la madre con la hija (idempotencia futura).
    decision["child_session"] = child_id
    if "abrir sesión hija para iterar" not in decision.get("next_steps", []):
        decision.setdefault("next_steps", []).append("abrir sesión hija para iterar")
    write_json(decision_path, decision)
    out_path = parent_dir / "session.output.json"
    if out_path.exists():
        out = load_json(out_path)
        out.get("decision", {})["child_session"] = child_id
        write_json(out_path, out)

    print(child_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
