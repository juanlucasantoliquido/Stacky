#!/usr/bin/env python3
"""Crea una nueva sesión de Kaizen desde las plantillas y la registra en el índice.

Portabilidad (ver ../PORTABILITY.md):
  - Solo librería estándar de Python 3. Sin red. Sin importar el proyecto padre.
  - Todas las rutas se resuelven RELATIVAS a la raíz kaizen/, calculada desde este archivo.
  - No realiza acciones destructivas: nunca sobrescribe una sesión existente.

Uso:
    python scripts/new_session.py "mejorar-mensajes-de-error"
    python scripts/new_session.py "Mejorar mensajes de error" --mode hitl --adapter generic
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

# Raíz kaizen/ = carpeta padre de scripts/. Independiente del cwd y del repo padre.
ROOT = Path(__file__).resolve().parent.parent

TEMPLATES = ROOT / "templates"
SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"
CONFIG = ROOT / "config" / "kaizen.config.yaml"

DEFAULT_MODE = "hitl"
DEFAULT_ADAPTER = "generic"


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-") or "sesion"


def utc_now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def read_config_value(key: str, default: str) -> str:
    """Lee un valor top-level de un YAML simple sin depender de PyYAML.

    Soporta solo claves planas tipo `clave: valor` (suficiente para mode/adapter).
    Si el archivo no existe o la clave no está, devuelve el default sin fallar.
    """
    if not CONFIG.exists():
        return default
    pattern = re.compile(r"^%s\s*:\s*(.+?)\s*(?:#.*)?$" % re.escape(key))
    try:
        for line in CONFIG.read_text(encoding="utf-8").splitlines():
            m = pattern.match(line)
            if m:
                return m.group(1).strip().strip('"').strip("'") or default
    except OSError:
        return default
    return default


def render(template_path: Path, mapping: dict) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in mapping.items():
        text = text.replace("{{%s}}" % key, str(value))
    return text


def append_to_index(entry: dict) -> None:
    if INDEX.exists():
        data = json.loads(INDEX.read_text(encoding="utf-8"))
    else:
        data = {"$schema_ref": "../contracts/session.input.schema.json", "sessions": []}
    data.setdefault("sessions", []).append(entry)
    INDEX.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Crea una nueva sesión de Kaizen.")
    parser.add_argument("objective", help="Objetivo de la sesión (frase o slug).")
    parser.add_argument("--mode", choices=["hitl", "aotl"], default=None)
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--parent", default=None, help="ID de la sesión madre (si es un iterate).")
    parser.add_argument("--tag", action="append", default=None,
                        help="Etiqueta (repetible): --tag infra --tag forense.")
    args = parser.parse_args(argv)

    mode = args.mode or read_config_value("mode", DEFAULT_MODE)
    adapter = args.adapter or read_config_value("adapter", DEFAULT_ADAPTER)

    now = utc_now()
    stamp = now.strftime("%Y-%m-%dT%H%M%SZ")
    slug = slugify(args.objective)
    base_id = "%s__%s" % (stamp, slug)

    # Evita colisiones de forma determinista: si el id ya existe (misma marca + slug),
    # agrega un sufijo incremental -2, -3, ... en vez de fallar.
    session_id = base_id
    suffix = 1
    while (SESSIONS / session_id).exists():
        suffix += 1
        session_id = "%s-%d" % (base_id, suffix)
    session_dir = SESSIONS / session_id

    (session_dir / "artifacts").mkdir(parents=True, exist_ok=False)

    created_utc = now.replace(microsecond=0).isoformat()
    mapping = {
        "SESSION_ID": session_id,
        "OBJECTIVE": args.objective,
        "MODE": mode,
        "ADAPTER": adapter,
        "CREATED_UTC": created_utc,
        "PARENT_SESSION": args.parent or "—",
    }

    # Bitácora + artefactos del ciclo desde plantillas.
    (session_dir / "session.md").write_text(
        render(TEMPLATES / "session.template.md", mapping), encoding="utf-8")
    (session_dir / "proposal.md").write_text(
        render(TEMPLATES / "proposal.template.md", mapping), encoding="utf-8")
    (session_dir / "evaluation.md").write_text(
        render(TEMPLATES / "evaluation.template.md", mapping), encoding="utf-8")
    (session_dir / "decision.md").write_text(
        render(TEMPLATES / "decision.template.md", mapping), encoding="utf-8")

    # Metadatos conforme a contracts/session.input.schema.json.
    session_json = {
        "id": session_id,
        "objective": args.objective,
        "mode": mode,
        "adapter": adapter,
        "created_utc": created_utc,
        "status": "open",
        "parent_session": args.parent,
        "context": {},
        "tags": args.tag or [],
    }
    (session_dir / "session.json").write_text(
        json.dumps(session_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    append_to_index({
        "id": session_id,
        "objective": args.objective,
        "mode": mode,
        "adapter": adapter,
        "created_utc": created_utc,
        "status": "open",
        "tags": args.tag or [],
    })

    # Ruta relativa a la raíz kaizen/ para no imprimir absolutas.
    print(session_dir.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
