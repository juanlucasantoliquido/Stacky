"""Plan 265 F7 — Bitácora de acciones de consola: auditoría local, mono-operador.

Registro append-only de qué acción disparó el operador desde la consola y
cuándo. Es REGISTRO, nunca RESTRICCIÓN (principio 3.4 del plan): ningún camino
de código consulta `read_console_audit` para decidir si permite una acción
(test 9 de F7 lo verifica leyendo el AST de este módulo y de api/executions.py).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import runtime_paths
from services.console_secret_mask import mask_secrets

_ALLOWED_ACTIONS = {"cancel", "relaunch", "copy_all", "open_full", "close"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — nunca crece sin techo
_FILENAME = "console_audit.jsonl"


def _audit_path() -> Path:
    """Ruta vía runtime_paths.data_dir() (NUNCA __file__): valida en dev y en
    el deploy congelado PyInstaller."""
    return runtime_paths.data_dir() / _FILENAME


def _audit_enabled() -> bool:
    from config import config as _cfg
    return bool(getattr(_cfg, "STACKY_CONSOLE_AUDIT_LOG_ENABLED", True))


def _rotate_if_needed(path: Path) -> None:
    """Si el archivo supera 5 MB, se renombra a .1 y se empieza de nuevo
    (máximo 2 archivos). Nada crece sin techo."""
    try:
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            rotated = path.with_name(path.name + ".1")
            if rotated.exists():
                rotated.unlink()
            path.rename(rotated)
    except OSError:
        pass


def _json_safe_detail(detail: dict | None) -> dict:
    """Descarta cualquier valor no serializable en vez de romper la escritura."""
    if not detail:
        return {}
    safe: dict = {}
    for key, value in detail.items():
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            continue
        safe[key] = value
    return safe


def _mask_detail(detail: dict) -> dict:
    """Enmascara (Plan 265 F4.5) todo valor de texto ANTES de escribir."""
    masked: dict = {}
    for key, value in detail.items():
        if isinstance(value, str):
            masked_value, _count = mask_secrets(value)
            masked[key] = masked_value
        else:
            masked[key] = value
    return masked


def record_console_action(*, execution_id: int, action: str, detail: dict | None = None) -> bool:
    """Append-only al archivo de bitácora en el directorio de datos de Stacky.

    - Una línea JSON por acción: {"ts","execution_id","action","detail"}.
    - `action` se valida contra una allowlist: si no está, se descarta y
      devuelve False (no se escribe basura).
    - Todo valor de texto de `detail` pasa por console_secret_mask.mask_secrets
      antes de escribirse (Plan 265 F4.5).
    - Rotación: si el archivo supera 5 MB, se renombra a .1 y se empieza de
      nuevo (máximo 2 archivos). Nada crece sin techo.
    - Devuelve False (sin lanzar) ante cualquier error de I/O o con la flag
      apagada. La auditoría NUNCA puede romper una acción del operador.
    """
    if not _audit_enabled():
        return False
    if action not in _ALLOWED_ACTIONS:
        return False
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(path)
        safe_detail = _mask_detail(_json_safe_detail(detail))
        entry = {
            "ts": time.time(),
            "execution_id": execution_id,
            "action": action,
            "detail": safe_detail,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def read_console_audit(limit: int = 200) -> list[dict]:
    """Últimas N entradas, más nuevas primero. [] ante cualquier problema."""
    if not _audit_enabled():
        return []
    try:
        path = _audit_path()
        if not path.exists():
            return []
        entries: list[dict] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue  # línea corrupta: se ignora, no rompe el resto
        entries.reverse()
        return entries[:limit]
    except OSError:
        return []
