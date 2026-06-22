#!/usr/bin/env python3
"""Self-check de regresión de Kaizen — verifica consistencia del ciclo. stdlib pura, solo-lectura.

Para cada sesión 'closed' en el índice, comprueba invariantes:
  - existe decision.json y session.output.json,
  - el verdict del índice coincide con el de decision.json,
  - decision.verdict es coherente con el status (accept/reject => closed),
  - los artefactos requeridos validan (reusa scripts/validate.py).

No crea ni muta sesiones (no contamina el índice ni el log). Pensado como guard de CI futuro.
Uso:
    python scripts/selfcheck.py        # exit 0 si todo es consistente
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import validate as _validate  # noqa: E402

SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    if not INDEX.exists():
        print("ERROR: no hay índice de sesiones", file=sys.stderr)
        return 1
    sessions = load_json(INDEX).get("sessions", [])
    failures = 0
    checked = 0

    for entry in sessions:
        sid = entry["id"]
        status = entry.get("status")
        if status != "closed":
            continue
        checked += 1
        sdir = SESSIONS / sid
        prefix = "  [%s]" % sid

        dec_path = sdir / "decision.json"
        out_path = sdir / "session.output.json"
        if not dec_path.exists():
            print("FAIL%s falta decision.json" % prefix); failures += 1; continue
        if not out_path.exists():
            print("FAIL%s falta session.output.json" % prefix); failures += 1; continue

        decision = load_json(dec_path)
        idx_verdict = entry.get("verdict")
        if decision.get("verdict") != idx_verdict:
            print("FAIL%s verdict índice=%s != decision=%s" %
                  (prefix, idx_verdict, decision.get("verdict"))); failures += 1; continue
        if decision.get("verdict") in ("accept", "reject") and status != "closed":
            print("FAIL%s verdict %s pero status %s" %
                  (prefix, decision.get("verdict"), status)); failures += 1; continue

        # Refuerzo forense: la sesión cerrada debe tener traza con un run.end.
        fpath = sdir / "forensic.jsonl"
        if not fpath.exists():
            print("FAIL%s falta forensic.jsonl" % prefix); failures += 1; continue
        if '"event": "run.end"' not in fpath.read_text(encoding="utf-8"):
            print("FAIL%s traza forense sin run.end" % prefix); failures += 1; continue

        # Validación de contratos (silenciada; solo nos importa el exit).
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = _validate.validate_session(sid, strict=False)
        if rc != 0:
            print("FAIL%s validate.py reportó errores:\n%s" % (prefix, buf.getvalue()))
            failures += 1
            continue

        print("OK  %s verdict=%s" % (prefix, decision.get("verdict")))

    print("\nself-check: %d sesiones cerradas revisadas, %d fallas." % (checked, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
