#!/usr/bin/env python3
"""Aplicador determinista y reversible de Kaizen (paso APLICAR del modo AOTL). stdlib pura.

El "cerebro" (engine.py) NUNCA toca el filesystem: produce un `change_set.json` declarativo.
Este módulo lo aplica de forma determinista, guardando la **pre-imagen** de cada archivo para
poder revertir SIN depender de git (rollback puro stdlib). git se usa solo, y opcionalmente,
para COMMITEAR una mejora aceptada, siempre scopeado a las rutas tocadas dentro de kaizen/.

Invariantes de seguridad (ver aotl_state.safe_target_path):
  - cada ruta debe quedar DENTRO de kaizen/,
  - nunca se tocan datos de sesión/decisiones ni la maquinaria del propio loop.

Formato de change_set.json:
  {
    "session_id": "...",
    "note": "texto opcional",
    "changes": [
      {"path": "playground/JOURNAL.md", "action": "modify", "content": "<contenido completo>"},
      {"path": "docs/nuevo.md",         "action": "create", "content": "..."},
      {"path": "obsoleto.md",           "action": "delete"}
    ]
  }

Uso:
    python scripts/apply.py <session_id>              # aplica change_set.json
    python scripts/apply.py <session_id> --rollback   # revierte lo aplicado
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
import aotl_state as st  # noqa: E402

enable_utf8()

VALID_ACTIONS = ("create", "modify", "delete")


def _apply_dir(root: Path, session_id: str) -> Path:
    return Path(root) / "sessions" / session_id / "_apply"


def validate_change_set(change_set: dict, root: Path = ROOT,
                        extra_protected: tuple[str, ...] = ()) -> list[str]:
    """Devuelve lista de errores (vacía = OK). No toca el filesystem."""
    errs: list[str] = []
    changes = change_set.get("changes")
    if not isinstance(changes, list) or not changes:
        return ["change_set sin 'changes' (lista no vacía)"]
    seen: set[str] = set()
    for i, ch in enumerate(changes):
        where = "changes[%d]" % i
        action = ch.get("action")
        path = ch.get("path")
        if action not in VALID_ACTIONS:
            errs.append("%s: action inválida %r" % (where, action))
        if not isinstance(path, str) or not path.strip():
            errs.append("%s: path vacío" % where)
            continue
        try:
            st.safe_target_path(path, root=root, extra_protected=extra_protected)
        except ValueError as exc:
            errs.append("%s: %s" % (where, exc))
        if path in seen:
            errs.append("%s: path duplicado %r" % (where, path))
        seen.add(path)
        if action in ("create", "modify") and not isinstance(ch.get("content"), str):
            errs.append("%s: action %s requiere 'content' string" % (where, action))
    return errs


def apply_change_set(session_id: str, change_set: dict, root: Path = ROOT,
                     extra_protected: tuple[str, ...] = ()) -> dict:
    """Aplica el change_set guardando pre-imágenes. Devuelve el manifiesto (applied.json).

    Lanza ValueError si el change_set no valida (no aplica nada).
    """
    root = Path(root)
    errs = validate_change_set(change_set, root=root, extra_protected=extra_protected)
    if errs:
        raise ValueError("change_set inválido:\n  - " + "\n  - ".join(errs))

    apply_dir = _apply_dir(root, session_id)
    backup_dir = apply_dir / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    created_dirs: list[str] = []
    for ch in change_set["changes"]:
        target = st.safe_target_path(ch["path"], root=root, extra_protected=extra_protected)
        rel = target.relative_to(root).as_posix()
        action = ch["action"]
        rec: dict = {"path": rel, "action": action, "pre_existed": target.exists()}

        if target.exists():
            backup = backup_dir / rel.replace("/", "__")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            rec["backup"] = backup.relative_to(root).as_posix()

        if action in ("create", "modify"):
            # Registrá los directorios que creamos, para poder limpiarlos en el rollback.
            parent = target.parent
            ancestors: list[Path] = []
            while not parent.exists() and root in parent.parents:
                ancestors.append(parent)
                parent = parent.parent
            for d in reversed(ancestors):
                d.mkdir(exist_ok=True)
                created_dirs.append(d.relative_to(root).as_posix())
            target.write_text(ch["content"], encoding="utf-8")
        elif action == "delete":
            if target.exists():
                target.unlink()
        records.append(rec)

    manifest = {
        "session_id": session_id,
        "applied_utc": st.utc_now(),
        "changes": records,
        "created_dirs": created_dirs,
    }
    st.write_json(apply_dir / "applied.json", manifest)
    return manifest


def rollback(session_id: str, root: Path = ROOT) -> int:
    """Revierte lo aplicado usando el manifiesto. Devuelve la cantidad de archivos restaurados."""
    root = Path(root)
    manifest_path = _apply_dir(root, session_id) / "applied.json"
    if not manifest_path.exists():
        return 0
    manifest = st.load_json(manifest_path)
    restored = 0
    # Orden inverso para deshacer de forma consistente.
    for rec in reversed(manifest.get("changes", [])):
        target = (root / rec["path"]).resolve()
        # Re-chequeo del guardarraíl: jamás revertir fuera de kaizen/.
        try:
            target.relative_to(Path(root).resolve())
        except ValueError:
            continue
        if rec.get("pre_existed"):
            backup = root / rec["backup"]
            if backup.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                restored += 1
        else:
            if target.exists():
                target.unlink()
                restored += 1
    # Limpiá directorios que creamos, si quedaron vacíos.
    for rel in sorted(manifest.get("created_dirs", []), key=len, reverse=True):
        d = root / rel
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass
    manifest["rolled_back_utc"] = st.utc_now()
    st.write_json(manifest_path, manifest)
    return restored


def applied_paths(session_id: str, root: Path = ROOT) -> list[str]:
    """Rutas (relativas a kaizen/) que siguen existiendo tras aplicar (para commitear)."""
    manifest_path = _apply_dir(root, session_id) / "applied.json"
    if not manifest_path.exists():
        return []
    out = []
    for rec in st.load_json(manifest_path).get("changes", []):
        out.append(rec["path"])
    return out


def commit_applied(session_id: str, message: str, root: Path = ROOT) -> tuple[bool, str]:
    """Commitea SOLO las rutas tocadas por esta sesión, scopeado a kaizen/. No falla el loop.

    Devuelve (ok, detalle). Si git no está disponible o no hay repo, devuelve (False, motivo)
    y el cambio simplemente queda en el árbol de trabajo (igual cuenta como implementado).
    """
    paths = applied_paths(session_id, root=root)
    if not paths:
        return False, "sin rutas para commitear"
    root = Path(root)
    try:
        add = subprocess.run(["git", "add", "--", *paths], cwd=str(root),
                             capture_output=True, text=True)
        if add.returncode != 0:
            return False, "git add falló: %s" % add.stderr.strip()
        commit = subprocess.run(["git", "commit", "-m", message, "--", *paths], cwd=str(root),
                                capture_output=True, text=True)
        if commit.returncode != 0:
            return False, "git commit falló: %s" % (commit.stderr.strip() or commit.stdout.strip())
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
                              capture_output=True, text=True)
        return True, head.stdout.strip()
    except FileNotFoundError:
        return False, "git no disponible"


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    do_rollback = "--rollback" in argv
    if not args:
        print("uso: python scripts/apply.py <session_id> [--rollback]", file=sys.stderr)
        return 2
    session_id = args[0]
    session_dir = ROOT / "sessions" / session_id
    if not session_dir.is_dir():
        print("ERROR: no existe la sesión %s" % session_id, file=sys.stderr)
        return 1

    if do_rollback:
        n = rollback(session_id)
        print("rollback: %d archivo(s) restaurado(s)." % n)
        return 0

    cs_path = session_dir / "change_set.json"
    if not cs_path.exists():
        print("ERROR: falta %s (¿el engine no propuso cambios?)" % cs_path, file=sys.stderr)
        return 1
    try:
        manifest = apply_change_set(session_id, st.load_json(cs_path))
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    print("aplicado: %d cambio(s)." % len(manifest["changes"]))
    for rec in manifest["changes"]:
        print("  %-7s %s" % (rec["action"], rec["path"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
