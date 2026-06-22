#!/usr/bin/env python3
"""Valida los artefactos de una sesión Kaizen contra los contratos. stdlib pura.

Chequea, para cada artefacto presente, los campos requeridos de su esquema (primer nivel) y
algunas restricciones simples (enums y rangos de scores). No depende de jsonschema para
preservar la portabilidad (ver PORTABILITY.md).

Uso:
    python scripts/validate.py <session_id>
    python scripts/validate.py <session_id> --strict   # exige proposal/evaluation/decision
Salida: imprime OK/errores; exit 0 si todo lo presente valida (y, con --strict, está completo).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
enable_utf8()

SESSIONS = ROOT / "sessions"
CONTRACTS = ROOT / "contracts"

ARTIFACTS = [
    ("session.json", "session.input.schema.json", False),
    ("proposal.json", "proposal.schema.json", True),
    ("evaluation.json", "evaluation.schema.json", True),
    ("decision.json", "decision.schema.json", True),
]

_SCORE_KEYS = ("value", "correctness", "scope", "reversibility", "measurability")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_required(obj: dict, schema: dict) -> list[str]:
    return ["falta campo requerido: %s" % k for k in schema.get("required", []) if k not in obj]


def check_enums(obj: dict, schema: dict) -> list[str]:
    errs = []
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key in obj and "enum" in spec and obj[key] not in spec["enum"]:
            errs.append("%s=%r no está en %s" % (key, obj[key], spec["enum"]))
    return errs


def check_patterns(obj: dict, schema: dict) -> list[str]:
    errs = []
    for key, spec in schema.get("properties", {}).items():
        pat = spec.get("pattern")
        if pat and key in obj and isinstance(obj[key], str):
            if not re.match(pat, obj[key]):
                errs.append("%s=%r no respeta el patrón %s" % (key, obj[key], pat))
    return errs


def check_scores(obj: dict, schema_name: str) -> list[str]:
    if schema_name != "evaluation.schema.json":
        return []
    errs = []
    scores = obj.get("scores", {})
    for k in _SCORE_KEYS:
        if k in scores and not (0 <= int(scores[k]) <= 3):
            errs.append("score %s=%s fuera de rango 0-3" % (k, scores[k]))
    if isinstance(obj.get("total"), int):
        computed = sum(int(scores.get(k, 0)) for k in _SCORE_KEYS)
        if obj["total"] != computed:
            errs.append("total=%s no coincide con suma de scores=%s" % (obj["total"], computed))
    return errs


def validate_session(session_id: str, strict: bool) -> int:
    session_dir = SESSIONS / session_id
    if not session_dir.is_dir():
        print("ERROR: no existe la sesión %s" % session_id, file=sys.stderr)
        return 1

    total_errors = 0
    for filename, schema_name, optional in ARTIFACTS:
        path = session_dir / filename
        if not path.exists():
            if strict and optional:
                print("FALTA  %s (requerido en --strict)" % filename)
                total_errors += 1
            else:
                print("skip   %s (ausente)" % filename)
            continue
        try:
            obj = load_json(path)
        except json.JSONDecodeError as exc:
            print("ERROR  %s: JSON inválido: %s" % (filename, exc))
            total_errors += 1
            continue
        schema = load_json(CONTRACTS / schema_name)
        errs = check_required(obj, schema) + check_enums(obj, schema) + \
            check_patterns(obj, schema) + check_scores(obj, schema_name)
        if errs:
            for e in errs:
                print("ERROR  %s: %s" % (filename, e))
            total_errors += len(errs)
        else:
            print("OK     %s" % filename)

    if total_errors:
        print("\n%d error(es) de validación." % total_errors)
        return 1
    print("\nTodos los artefactos presentes validan.")
    return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    if not args:
        print("uso: python scripts/validate.py <session_id> [--strict]", file=sys.stderr)
        return 2
    return validate_session(args[0], strict)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
