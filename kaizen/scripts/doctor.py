#!/usr/bin/env python3
"""Diagnóstico de salud estructural de Kaizen — 'kaizen doctor'. stdlib pura, solo-lectura.

Verifica que la instalación esté operativa: config activa parseable, perfil existente, adapter
configurado presente, contratos y scripts en su lugar, índice válido. No muta nada.

Uso:
    python scripts/doctor.py        # exit 0 si no hay FAIL
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _config import load_yaml  # noqa: E402
from _console import enable_utf8  # noqa: E402
enable_utf8()

CONFIG = ROOT / "config" / "kaizen.config.yaml"
CONTRACTS = ROOT / "contracts"

_REQUIRED_CONTRACTS = [
    "session.input.schema.json", "proposal.schema.json", "evaluation.schema.json",
    "decision.schema.json", "artifact.schema.json", "session.output.schema.json",
]
_REQUIRED_SCRIPTS = [
    "new_session.py", "run_session.py", "validate.py", "metrics.py", "selfcheck.py",
]


def main(argv: list[str]) -> int:
    checks: list[tuple[str, str, str]] = []  # (nivel, item, detalle)

    def add(level, item, detail=""):
        checks.append((level, item, detail))

    # Config
    if not CONFIG.exists():
        add("WARN", "config activa", "falta config/kaizen.config.yaml (se usarán defaults)")
        cfg = {}
    else:
        try:
            cfg = load_yaml(CONFIG)
            add("OK", "config activa", "mode=%s adapter=%s profile=%s" %
                (cfg.get("mode"), cfg.get("adapter"), cfg.get("profile", "default")))
        except Exception as exc:  # noqa: BLE001
            add("FAIL", "config activa", "no parsea: %s" % exc)
            cfg = {}

    # Perfil
    profile_name = cfg.get("profile", "default")
    profile_path = ROOT / "config" / "profiles" / ("%s.yaml" % profile_name)
    if profile_path.exists():
        try:
            load_yaml(profile_path)
            add("OK", "perfil", profile_name)
        except Exception as exc:  # noqa: BLE001
            add("FAIL", "perfil", "no parsea: %s" % exc)
    else:
        add("FAIL", "perfil", "falta %s" % profile_path.relative_to(ROOT).as_posix())

    # Adapter
    adapter = cfg.get("adapter", "generic")
    adapter_dir = ROOT / "adapters" / adapter
    if adapter_dir.is_dir():
        add("OK" if (adapter_dir / "adapter.yaml").exists() else "WARN",
            "adapter '%s'" % adapter,
            "" if (adapter_dir / "adapter.yaml").exists() else "sin adapter.yaml")
    else:
        add("FAIL", "adapter '%s'" % adapter, "no existe adapters/%s/" % adapter)

    # Contratos
    missing_c = [c for c in _REQUIRED_CONTRACTS if not (CONTRACTS / c).exists()]
    add("OK" if not missing_c else "FAIL", "contratos",
        "completos" if not missing_c else "faltan %s" % missing_c)

    # Scripts
    missing_s = [s for s in _REQUIRED_SCRIPTS if not (ROOT / "scripts" / s).exists()]
    add("OK" if not missing_s else "FAIL", "scripts núcleo",
        "presentes" if not missing_s else "faltan %s" % missing_s)

    # Índice
    idx = ROOT / "sessions" / "_index.json"
    if idx.exists():
        try:
            json.loads(idx.read_text(encoding="utf-8"))
            add("OK", "índice de sesiones", "válido")
        except Exception as exc:  # noqa: BLE001
            add("FAIL", "índice de sesiones", "JSON inválido: %s" % exc)
    else:
        add("WARN", "índice de sesiones", "no existe aún")

    # Render
    print("KAIZEN doctor — diagnóstico estructural")
    print("-" * 56)
    fails = warns = 0
    for level, item, detail in checks:
        mark = {"OK": "ok ", "WARN": "!! ", "FAIL": "XX "}[level]
        fails += level == "FAIL"
        warns += level == "WARN"
        print(" %s %-22s %s" % (mark, item, detail))
    print("-" * 56)
    print("resultado: %d OK, %d warnings, %d fallas" %
          (len(checks) - fails - warns, warns, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
