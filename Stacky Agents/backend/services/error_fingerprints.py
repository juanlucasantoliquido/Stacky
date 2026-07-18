"""Plan 163 F5 — loader + scanner del catalogo de huellas de regresion.

Fuente UNICA de la logica de grep (el smoke de PowerShell consume el MISMO
catalogo). Sustrato del futuro plan de analisis local de logs con clustering."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from runtime_paths import backend_root

_BOOT_SCAN_TAIL_BYTES = 5_000_000  # tail acotado: logs enormes no degradan el arranque


def catalog_path() -> Path:
    return backend_root().parent / "docs" / "sistema" / "error_fingerprints.json"


def load_fingerprints() -> list[dict]:
    data = json.loads(catalog_path().read_text(encoding="utf-8"))
    return data.get("fingerprints", [])


def guarded_fingerprints(fingerprints: list[dict] | None = None) -> list[dict]:
    """Solo las huellas que el smoke NEGATIVO debe alarmar: resolved + log_guarded."""
    fps = fingerprints if fingerprints is not None else load_fingerprints()
    return [fp for fp in fps if fp.get("status") == "resolved" and fp.get("log_guarded") is True]


def scan_text(text: str, fingerprints: list[dict] | None = None) -> list[str]:
    """Devuelve los ids de huellas GUARDADAS cuyo patron aparece en el texto."""
    hits: list[str] = []
    for fp in guarded_fingerprints(fingerprints):
        if re.search(fp["log_pattern"], text):
            hits.append(fp["id"])
    return hits


def _latest_log_file() -> Path | None:
    """El stacky-*.log mas reciente en logs_dir(), o None si no hay."""
    try:
        from services.local_file_logging import logs_dir
        candidates = sorted(logs_dir().glob("stacky-*.log"), key=lambda p: p.stat().st_mtime)
        return candidates[-1] if candidates else None
    except Exception:  # noqa: BLE001
        return None


def run_boot_scan() -> list[str]:
    """Escanea el TAIL del log mas reciente al arrancar. AVISA, no actua.

    - No-op bajo STACKY_TEST_MODE (los tests lo llaman directo con fixtures).
    - Nunca lanza: cualquier fallo degrada a [] con logger.debug.
    - Si hay hits: UNA fila system_logs WARNING source="fingerprint_scan"
      action="regression_detected" + logger.warning. Log limpio: no escribe nada.
    """
    if os.environ.get("STACKY_TEST_MODE", "").strip().lower() in ("1", "true", "yes"):
        return []
    try:
        target = _latest_log_file()
        if target is None:
            return []
        size = target.stat().st_size
        with target.open("rb") as fh:
            if size > _BOOT_SCAN_TAIL_BYTES:
                fh.seek(size - _BOOT_SCAN_TAIL_BYTES)
            text = fh.read().decode("utf-8", errors="replace")
        hits = scan_text(text)
        if hits:
            import json as _json
            import logging
            from db import session_scope
            from models import SystemLog
            logging.getLogger("stacky.services.error_fingerprints").warning(
                "boot-scan: huellas de regresion detectadas en %s: %s", target.name, hits
            )
            with session_scope() as session:
                session.add(SystemLog(
                    level="WARNING", source="fingerprint_scan", action="regression_detected",
                    context_json=_json.dumps({"hits": hits, "log": target.name}),
                ))
        return hits
    except Exception:  # noqa: BLE001 — el boot-scan jamas rompe el arranque
        return []
