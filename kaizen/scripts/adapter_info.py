#!/usr/bin/env python3
"""Resuelve y describe el adapter activo. 'kaizen adapter'. stdlib pura, solo-lectura.

Lee el adapter configurado en config/kaizen.config.yaml (o 'generic' por defecto), carga su
adapter.yaml y verifica los campos que exige adapters/adapter.contract.md. No nombra ningún
adapter de forma fija: lo resuelve por configuración (mantiene el núcleo portable).

Uso:
    python scripts/adapter_info.py            # adapter activo
    python scripts/adapter_info.py --list     # lista todos los adapters disponibles
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _config import load_yaml  # noqa: E402

CONFIG = ROOT / "config" / "kaizen.config.yaml"
ADAPTERS = ROOT / "adapters"
_REQUIRED = ["name", "description", "observe", "engine", "apply", "measure"]


def active_adapter() -> str:
    if CONFIG.exists():
        return load_yaml(CONFIG).get("adapter", "generic")
    return "generic"


def list_adapters() -> list[str]:
    return sorted(p.name for p in ADAPTERS.iterdir()
                  if p.is_dir() and (p / "adapter.yaml").exists())


def describe(name: str) -> int:
    path = ADAPTERS / name / "adapter.yaml"
    if not path.exists():
        print("ERROR: adapter '%s' no tiene adapter.yaml" % name, file=sys.stderr)
        return 1
    data = load_yaml(path)
    missing = [k for k in _REQUIRED if k not in data]
    print("Adapter activo: %s" % name)
    print("  descripción: %s" % data.get("description", "—"))
    print("  campos del contrato: %s" %
          ("completos" if not missing else "FALTAN %s" % missing))
    for k in ("observe", "engine", "apply", "measure"):
        v = data.get(k)
        print("  %-8s: %s" % (k, v if not isinstance(v, dict) else
                              ", ".join("%s=%s" % (kk, vv) for kk, vv in v.items())))
    return 1 if missing else 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        print("Adapters disponibles: %s" % ", ".join(list_adapters()))
        print("Activo: %s" % active_adapter())
        return 0
    return describe(active_adapter())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
