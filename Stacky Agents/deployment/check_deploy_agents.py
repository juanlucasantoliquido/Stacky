#!/usr/bin/env python3
"""Pre-release validation: comprueba que ``<deploy>/Stacky/agents`` esté
materializado correctamente antes de publicar un release.

Uso::

    python check_deploy_agents.py --stacky-home <deploy>/Stacky
    python check_deploy_agents.py --deploy-root <deploy>

El script:

- Verifica que ``<stacky_home>/agents`` exista.
- Verifica que contenga al menos un ``*.agent.md``.
- Verifica que ``manifest.json`` exista y siga el schema versionado.
- Verifica que los ``checksum_sha256`` declarados coincidan con el contenido
  real de cada ``.agent.md`` (detecta corrupción durante la publicación).
- Devuelve exit code 0 si todo OK, 1 si encuentra problemas.

Plan: ``plan-agentes-bundled-en-stacky-2026-05-29.md`` §5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(stacky_home: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    agents_dir = stacky_home / "agents"

    if not stacky_home.is_dir():
        return False, [f"STACKY_HOME no existe o no es directorio: {stacky_home}"]

    if not agents_dir.is_dir():
        return False, [f"Stacky/agents no existe: {agents_dir}"]

    agent_files = sorted(agents_dir.glob("*.agent.md"))
    if not agent_files:
        errors.append(f"No hay *.agent.md en {agents_dir}")

    manifest_path = agents_dir / "manifest.json"
    if not manifest_path.is_file():
        errors.append(f"falta manifest.json: {manifest_path}")
        return False, errors

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, [f"manifest.json no es JSON válido: {exc}"]

    if not isinstance(manifest, dict) or "agents" not in manifest:
        return False, ["manifest.json no tiene clave 'agents'"]

    if manifest.get("schema_version") != 1:
        errors.append(
            f"schema_version inesperado: {manifest.get('schema_version')} (esperado 1)"
        )

    declared_filenames = set()
    for agent in manifest["agents"]:
        if not isinstance(agent, dict):
            errors.append("entry no-objeto en manifest.agents")
            continue
        for required in ("name", "mention", "filename", "checksum_sha256", "source"):
            if required not in agent:
                errors.append(f"falta '{required}' en entry {agent.get('filename')}")
        filename = agent.get("filename")
        if not isinstance(filename, str):
            continue
        declared_filenames.add(filename)
        target = agents_dir / filename
        if not target.is_file():
            errors.append(f"{filename} declarado en manifest pero no existe en disco")
            continue
        actual = _sha256(target)
        expected = agent.get("checksum_sha256")
        if actual != expected:
            errors.append(
                f"checksum no coincide para {filename}: "
                f"esperado={expected}, actual={actual}"
            )

    # detectar archivos en disco no declarados en el manifest
    for path in agent_files:
        if path.name not in declared_filenames:
            errors.append(f"{path.name} presente en disco pero no en manifest.json")

    return (len(errors) == 0), errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stacky-home", type=Path, help="Ruta a la carpeta Stacky/")
    group.add_argument(
        "--deploy-root",
        type=Path,
        help="Ruta al root del deploy; se asume Stacky/ adentro.",
    )
    args = parser.parse_args(argv)

    if args.stacky_home is not None:
        stacky_home = args.stacky_home
    else:
        stacky_home = args.deploy_root / "Stacky"

    stacky_home = stacky_home.expanduser().resolve()
    ok, errors = validate(stacky_home)

    if ok:
        print(f"OK Stacky/agents en {stacky_home / 'agents'}")
        return 0

    print(f"FAIL Stacky/agents en {stacky_home / 'agents'}", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
