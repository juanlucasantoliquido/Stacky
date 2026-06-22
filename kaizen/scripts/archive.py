#!/usr/bin/env python3
"""Archiva una sesión cerrada (housekeeping). 'kaizen archive'. stdlib pura.

Marca la entrada del índice con status 'archived' para sacarla del foco operativo sin borrar
nada (la carpeta de la sesión y su traza forense se conservan). Idempotente y no destructivo.
Sólo archiva sesiones 'closed'.

Uso:
    python scripts/archive.py <session_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
enable_utf8()

INDEX = ROOT / "sessions" / "_index.json"


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: python scripts/archive.py <session_id>", file=sys.stderr)
        return 2
    sid = argv[0]
    if not INDEX.exists():
        print("ERROR: no hay índice", file=sys.stderr)
        return 1
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    entry = next((s for s in data.get("sessions", []) if s.get("id") == sid), None)
    if entry is None:
        print("ERROR: sesión %s no está en el índice" % sid, file=sys.stderr)
        return 1
    if entry.get("status") == "archived":
        print("ya archivada: %s" % sid)  # idempotente
        return 0
    if entry.get("status") != "closed":
        print("ERROR: sólo se archivan sesiones 'closed' (status=%s)" % entry.get("status"),
              file=sys.stderr)
        return 1
    entry["status"] = "archived"
    INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("archivada: %s" % sid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
