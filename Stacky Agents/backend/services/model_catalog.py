"""Plan 159 v2 — catálogo único de modelos/efforts por runtime, leído de disco
con caché invalidada por mtime (sin restart, sin redeploy de frontend).
Resolución de ruta vía runtime_paths.backend_root(): válida en dev (backend/)
y en el deploy congelado PyInstaller (dir del exe). PROHIBIDO usar __file__
para esta ruta (C1)."""
from pathlib import Path
import json
import logging
import os
import time

import runtime_paths

logger = logging.getLogger(__name__)

TTL_SEC = 300  # único literal del TTL; el endpoint lo reexpone tal cual (C8)


def _catalog_path() -> Path:
    # C1: backend_root() = dir del exe en frozen / backend/ en dev.
    # Mismo patrón que config.py con backend_root()/.env
    # (build_release.ps1 copia el archivo junto al exe).
    return runtime_paths.backend_root() / "config" / "model_catalog.json"


_EMERGENCY_FALLBACK: dict = {
    "runtimes": {
        "claude_code_cli": {
            "source": "emergency_fallback", "default_model": "claude-sonnet-5",
            "default_effort": "medium",
            "models": [{"id": "claude-sonnet-5", "label": "Sonnet 5"}],
            "efforts": [{"id": "medium", "label": "medium"}],
            "effort_support": {},
        },
        "codex_cli": {"source": "emergency_fallback", "default_model": "", "default_effort": None,
                       "models": [{"id": "", "label": "Automático"}], "efforts": [], "effort_support": {}},
        "github_copilot": {"source": "emergency_fallback", "default_model": None, "default_effort": None,
                            "models": [], "efforts": [], "effort_support": {}},
    }
}

_cache: dict = {"data": None, "loaded_at": 0.0, "mtime": None}
_copilot_cache: dict = {"models": None, "loaded_at": 0.0, "error": None}


def load_model_catalog(force_refresh: bool = False) -> dict:
    """Devuelve {"fallback_used": bool, "error": str|None, "loaded_at": float,
    "runtimes": {...}}.

    Relee el archivo si: force_refresh=True, TTL expiró, o el mtime cambió
    desde la última lectura. Nunca lanza — cualquier fallo cae al fallback
    de emergencia embebido.
    """
    now = time.time()
    path = _catalog_path()
    try:
        current_mtime = os.path.getmtime(path)
    except OSError:
        current_mtime = None

    stale = (
        force_refresh
        or _cache["data"] is None
        or (now - _cache["loaded_at"]) > TTL_SEC
        or current_mtime != _cache["mtime"]
    )
    if not stale:
        return _cache["data"]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "runtimes" not in raw:
            raise ValueError("model_catalog.json sin clave 'runtimes'")
        result = {"fallback_used": False, "error": None, "loaded_at": now,
                  "runtimes": raw["runtimes"]}
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog: fallback de emergencia (%s)", e)
        result = {"fallback_used": True, "error": str(e), "loaded_at": now,
                  "runtimes": _EMERGENCY_FALLBACK["runtimes"]}

    _cache.update(data=result, loaded_at=now, mtime=current_mtime)
    return result


def get_copilot_models_cached(force_refresh: bool = False) -> dict:
    """C3: introspección viva de github_copilot con caché propio (TTL_SEC) y
    timeout corto (5s, no los 15 default de copilot_bridge). Devuelve
    {"models": [...], "error": str|None}. Nunca lanza. Un fallo también se
    cachea TTL_SEC (no martillar una red caída); ?refresh=true lo fuerza."""
    now = time.time()
    if (not force_refresh and _copilot_cache["models"] is not None
            and (now - _copilot_cache["loaded_at"]) <= TTL_SEC):
        return {"models": _copilot_cache["models"], "error": _copilot_cache["error"]}
    try:
        import copilot_bridge
        raw = copilot_bridge.list_copilot_models(timeout_sec=5)
        models = [
            {"id": m.get("id"), "label": m.get("name") or m.get("id"), "recommended": False}
            for m in raw if m.get("id")
        ]
        _copilot_cache.update(models=models, loaded_at=now, error=None)
    except Exception as e:  # noqa: BLE001
        logger.warning("model_catalog: introspección copilot falló (%s)", e)
        _copilot_cache.update(models=[], loaded_at=now, error=str(e))
    return {"models": _copilot_cache["models"], "error": _copilot_cache["error"]}
