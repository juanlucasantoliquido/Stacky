#!/usr/bin/env python3
"""Estado compartido del modo AOTL (Agent-on-the-Loop) de Kaizen. stdlib pura.

Centraliza lo que comparten el loop de automejora, el aplicador y el dashboard:
  - `impl_status`: estado de IMPLEMENTACIÓN de cada sesión en el índice
    (planned/applied/implemented/rejected/iterating/escalated/reverted).
  - El estado vivo del loop (`sessions/_loop.status.json`) que el dashboard lee para
    mostrar "qué está haciendo ahora".
  - El flag de parada cooperativa (`sessions/_loop.stop`): el loop lo chequea entre vueltas.
  - El **guardarraíl de rutas**: a qué archivos puede tocar el auto-apply. SOLO dentro de
    `kaizen/`, NUNCA datos de sesión/decisiones ni la propia maquinaria del loop.

No importa el proyecto padre. No usa red. Reversibilidad y seguridad son responsabilidad
de quien llama (ver apply.py), acá viven solo las invariantes compartidas.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"
LOOP_STATUS = SESSIONS / "_loop.status.json"
STOP_FLAG = SESSIONS / "_loop.stop"

# --- impl_status canónicos (estado de implementación, ortogonal al status del ciclo) -------
PLANNED = "planned"          # propuesta escrita; todavía no aplicada
APPLIED = "applied"          # change_set aplicado al árbol (tentativo, pre-veredicto)
IMPLEMENTED = "implemented"  # aceptado por el gate Y conservado (opcionalmente commiteado)
REJECTED = "rejected"        # gate rechazó; cambio revertido
ITERATING = "iterating"      # gate iterate (no escalado); revertido; hija engendrada
ESCALATED = "escalated"      # gate escaló a humano; revertido; loop en pausa
REVERTED = "reverted"        # revertido sin un veredicto terminal (p.ej. error/cancelación)
ALL_IMPL_STATUS = (PLANNED, APPLIED, IMPLEMENTED, REJECTED, ITERATING, ESCALATED, REVERTED)

# --- Guardarraíl de rutas para el auto-apply ------------------------------------------------
# Prefijos (primer segmento relativo a kaizen/) que el loop NUNCA puede editar.
PROTECTED_PREFIXES = ("sessions", "decisions", "artifacts", ".git")
# Archivos puntuales protegidos: la maquinaria del propio loop (evita que se autosabotee
# en caliente) y la config activa.
PROTECTED_FILES = (
    ".gitignore",
    "kaizen.py",
    "config/kaizen.config.yaml",
    "scripts/aotl_state.py",
    "scripts/apply.py",
    "scripts/autoloop.py",
    "scripts/engine.py",
    "scripts/dashboard.py",
    # Maquinaria critica del arnes: gate, validacion, forense, ciclo de sesiones.
    # El loop AOTL NO debe auto-editarlos para evitar autosabotaje en caliente.
    "scripts/run_session.py",
    "scripts/validate.py",
    "scripts/forensic.py",
    "scripts/new_session.py",
    "scripts/selfcheck.py",
    "scripts/spawn_child.py",
    "scripts/promote_decision.py",
)


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, obj: dict) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# --- Índice: campos de implementación -------------------------------------------------------
def update_index_fields(session_id: str, fields: dict, index: Path = INDEX) -> None:
    """Mergea `fields` en la entrada del índice de `session_id`. No-op si no existe el índice."""
    if not Path(index).exists():
        return
    data = load_json(index)
    for entry in data.get("sessions", []):
        if entry.get("id") == session_id:
            entry.update(fields)
            break
    write_json(index, data)


def set_impl_status(session_id: str, impl_status: str, index: Path = INDEX, **extra) -> None:
    if impl_status not in ALL_IMPL_STATUS:
        raise ValueError("impl_status desconocido: %r" % impl_status)
    fields = {"impl_status": impl_status, "auto": True}
    fields.update(extra)
    update_index_fields(session_id, fields, index=index)


# --- Estado vivo del loop -------------------------------------------------------------------
def write_loop_status(status: dict, path: Path = LOOP_STATUS) -> None:
    status = dict(status)
    status["updated_utc"] = utc_now()
    write_json(path, status)


def read_loop_status(path: Path = LOOP_STATUS) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return load_json(p)
    except (json.JSONDecodeError, OSError):
        return None


def clear_loop_status(path: Path = LOOP_STATUS) -> None:
    Path(path).unlink(missing_ok=True)


# --- Parada cooperativa ---------------------------------------------------------------------
def request_stop(path: Path = STOP_FLAG, reason: str = "manual") -> None:
    Path(path).write_text(json.dumps({"reason": reason, "requested_utc": utc_now()}) + "\n",
                          encoding="utf-8")


def stop_requested(path: Path = STOP_FLAG) -> bool:
    return Path(path).exists()


def clear_stop(path: Path = STOP_FLAG) -> None:
    Path(path).unlink(missing_ok=True)


# --- Guardarraíl de rutas -------------------------------------------------------------------
def is_protected(rel_posix: str, extra_protected: tuple[str, ...] = ()) -> bool:
    first = rel_posix.split("/", 1)[0]
    if first in PROTECTED_PREFIXES:
        return True
    if rel_posix in PROTECTED_FILES or rel_posix in extra_protected:
        return True
    return False


def safe_target_path(target: str, root: Path = ROOT,
                     extra_protected: tuple[str, ...] = ()) -> Path:
    """Resuelve `target` (relativo a `root`) y verifica que sea editable por el loop.

    Reglas duras (lanza ValueError si se violan):
      - debe quedar DENTRO de `root` (bloquea '..' y rutas absolutas externas),
      - no puede caer en un prefijo/archivo protegido (datos de sesión, maquinaria del loop).
    """
    root = Path(root).resolve()
    raw = Path(target)
    p = (raw if raw.is_absolute() else root / raw).resolve()
    try:
        rel = p.relative_to(root)
    except ValueError:
        raise ValueError("ruta fuera de kaizen/: %r" % target)
    rel_posix = rel.as_posix()
    if not rel_posix or rel_posix == ".":
        raise ValueError("ruta vacía o igual a la raíz: %r" % target)
    if is_protected(rel_posix, extra_protected):
        raise ValueError("ruta protegida (no editable por el loop): %s" % rel_posix)
    return p
