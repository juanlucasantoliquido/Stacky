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
        # Plan 212 F3 — el fallback de emergencia NUNCA puede ofrecer menos que el
        # archivo: si el JSON no se puede leer, el operador tiene que seguir viendo
        # el catálogo completo, no una lista mutilada que le esconde modelos.
        "claude_code_cli": {
            "source": "emergency_fallback", "default_model": "claude-sonnet-5",
            "default_effort": "medium",
            "models": [
                {"id": "claude-opus-5", "label": "Opus 5 (máxima calidad)", "recommended": False},
                {"id": "claude-sonnet-5", "label": "Sonnet 5 (recomendado)", "recommended": True},
                {"id": "claude-opus-4-8", "label": "Opus 4.8"},
                {"id": "claude-haiku-4-5", "label": "Haiku 4.5"},
                {"id": "claude-sonnet-4-6", "label": "Sonnet 4.6"},
            ],
            "efforts": [
                {"id": "low", "label": "low"},
                {"id": "medium", "label": "medium"},
                {"id": "high", "label": "high"},
                {"id": "xhigh", "label": "xhigh"},
                {"id": "max", "label": "max"},
            ],
            "effort_support": {
                "claude-haiku-4-5": ["low", "medium", "high"],
                "claude-sonnet-5": ["low", "medium", "high", "max"],
                "claude-sonnet-4-6": ["low", "medium", "high", "max"],
                "claude-opus-4-8": ["low", "medium", "high", "xhigh", "max"],
                "claude-opus-5": ["low", "medium", "high", "xhigh", "max"],
            },
            "effort_degrade": {
                "claude-haiku-4-5": {"xhigh": "high", "max": "high"},
                "claude-sonnet-5": {"xhigh": "high"},
                "claude-sonnet-4-6": {"xhigh": "high"},
                "claude-opus-4-8": {},
                "claude-opus-5": {},
            },
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

    result = _merge_probe(result)
    _cache.update(data=result, loaded_at=now, mtime=current_mtime)
    return result


def _merge_probe(catalog: dict) -> dict:
    """Plan 212 F6 — Suma al catálogo lo que el CLI instalado declara tener.

    UNION, nunca resta: un modelo del archivo que el probe no liste se conserva.
    El probe puede ser incompleto (formato desconocido, versión vieja del CLI) y
    restar rompería una selección que el operador ya venía usando.

    Corre una vez por refresco de caché (TTL 300s), no por request.
    """
    try:
        import config as _config

        if not getattr(_config.config, "STACKY_MODEL_PROBE_ENABLED", False):
            return catalog
        # Bajo pytest no se spawnean procesos: un test del catálogo no tiene por
        # qué depender de si hay un CLI instalado en la máquina, ni pagar su
        # timeout. Mismo criterio que los otros daemons del arranque.
        if os.environ.get("STACKY_TEST_MODE", "").strip().lower() in ("1", "true", "yes"):
            return catalog

        cli = (catalog.get("runtimes") or {}).get("claude_code_cli")
        if not isinstance(cli, dict):
            return catalog

        from services.claude_code_cli_runner import _resolve_claude_code_cli_bin
        from services.model_probe import probe_claude_models

        try:
            binario = _resolve_claude_code_cli_bin()
        except Exception:  # noqa: BLE001 — sin CLI no hay nada que descubrir
            binario = ""

        resultado = probe_claude_models(cli_bin=binario)

        conocidos = {m.get("id") for m in (cli.get("models") or [])}
        agregados: list = []
        for mid in resultado.models:
            if mid in conocidos:
                continue
            cli.setdefault("models", []).append({
                "id": mid,
                "label": f"{mid} (detectado en el CLI)",
                "recommended": False,
            })
            conocidos.add(mid)
            agregados.append(mid)

        if agregados:
            # Sin effort_support propio: el clamp decide por familia del nombre,
            # así que un modelo descubierto degrada coherente sin config extra.
            cli["source"] = "static_config_file+live_probe"
        cli["probe"] = {
            "ok": resultado.ok,
            "command": resultado.command,
            "reason": resultado.reason,
            "added": agregados,
        }
        return catalog
    except Exception:  # noqa: BLE001 — el catálogo nunca cae por el probe
        logger.debug("model_catalog: probe falló (no crítico)", exc_info=True)
        return catalog


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
