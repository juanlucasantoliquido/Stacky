"""
FA-04 — Multi-LLM routing.

Por agente + complejidad estimada del input, elegir el modelo óptimo.

Backends soportados:
- anthropic / mock: Claude Haiku/Sonnet/Opus.
- copilot: modelos reales habilitados en GitHub Copilot del usuario (consulta `/models`).

El operador puede forzar un modelo específico en el editor (override).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from config import config

logger = logging.getLogger("stacky_agents.llm_router")


CLAUDE_MODELS = ["claude-haiku-4-5", "claude-sonnet-4-6"]
MOCK_MODELS = ["mock-1.0"]

# §5.2 — cap duro: NUNCA un modelo Claude superior a Sonnet 4.6.
# Cualquier tier prohibido (opus / fable) se mapea a este tope.
CLAUDE_CAP_MODEL = "claude-sonnet-4-6"
_FORBIDDEN_CLAUDE_TIER = ("opus", "fable")


def clamp_model(model: str | None) -> str:
    """Aplica el cap duro de §5.2 sobre un id de modelo Claude.

    Mapea cualquier modelo de tier prohibido (opus, fable) a CLAUDE_CAP_MODEL.
    Modelos permitidos (haiku/sonnet) y no-Claude (copilot/mock) pasan sin tocar.
    Es la ÚNICA función que decide qué está capado; toda decisión Claude pasa por acá.
    """
    if not model:
        return CLAUDE_CAP_MODEL
    low = model.lower()
    if low.startswith("claude-") and any(t in low for t in _FORBIDDEN_CLAUDE_TIER):
        return CLAUDE_CAP_MODEL
    return model



_CACHE_TTL_SEC = 300
_cache_lock = threading.Lock()
_cached_models: list[dict] | None = None
_cached_at: float = 0.0
_cached_error: str | None = None


def _refresh_copilot_models(force: bool = False) -> tuple[list[dict], str | None]:
    """Devuelve (modelos, error). Si la consulta falla, error se loguea pero no se levanta."""
    global _cached_models, _cached_at, _cached_error
    now = time.time()
    with _cache_lock:
        fresh = _cached_models is not None and (now - _cached_at) < _CACHE_TTL_SEC
        if fresh and not force:
            return list(_cached_models or []), _cached_error
    try:
        from copilot_bridge import list_copilot_models  # import diferido para evitar ciclos
        models = list_copilot_models()
    except Exception as e:
        logger.warning("no pude listar modelos de Copilot: %s", e)
        with _cache_lock:
            _cached_at = now
            _cached_error = str(e)
            return list(_cached_models or []), _cached_error
    with _cache_lock:
        _cached_models = models
        _cached_at = now
        _cached_error = None
        return list(models), None


def get_copilot_models(refresh: bool = False) -> list[dict]:
    models, _ = _refresh_copilot_models(force=refresh)
    return models


def get_copilot_models_status(refresh: bool = False) -> dict:
    models, error = _refresh_copilot_models(force=refresh)
    with _cache_lock:
        cached_at = _cached_at
    return {
        "models": models,
        "error": error,
        "cached_at": cached_at,
        "ttl_sec": _CACHE_TTL_SEC,
        "fallback": not models,
    }


def _available_models() -> list[str]:
    backend = (config.LLM_BACKEND or "mock").lower()
    if backend == "vscode_bridge":
        from copilot_bridge import list_vscode_bridge_models
        live = list_vscode_bridge_models()
        return [m["id"] for m in live]
    if backend == "copilot":
        live = get_copilot_models()
        return [m["id"] for m in live]  # vacío si la auth falla — sin fallback
    if backend == "mock":
        return MOCK_MODELS + CLAUDE_MODELS
    return CLAUDE_MODELS + MOCK_MODELS


# Mantener compatibilidad con código existente que lee este símbolo.
AVAILABLE_MODELS = _available_models()


@dataclass
class RoutingDecision:
    model: str
    reason: str

    def to_dict(self) -> dict:
        return {"model": self.model, "reason": self.reason}


# Default por agente para Claude.
DEFAULT_BY_AGENT_CLAUDE: dict[str, str] = {
    "business":   "claude-sonnet-4-6",
    "functional": "claude-sonnet-4-6",
    "technical":  "claude-sonnet-4-6",
    "developer":  "claude-sonnet-4-6",
    "qa":         "claude-haiku-4-5",
}


def _pick_copilot_default(agent_type: str, available: list[str]) -> str:
    """Default razonable para Copilot a partir de la lista real disponible."""
    if not available:
        from config import config as _cfg
        if (_cfg.LLM_BACKEND or "").lower() == "vscode_bridge":
            raise RuntimeError(
                "El bridge de VS Code no responde para el proyecto activo. "
                "Recargá VS Code: Ctrl+Shift+P → 'Developer: Reload Window'"
            )
        raise RuntimeError(
            "No hay modelos de Copilot disponibles. Verificá que gh auth esté autenticado "
            "y que la cuenta tenga acceso a GitHub Copilot."
        )
    # IDs cortos del GitHub Models catalog (sin prefijo publisher/)
    preference_main = [
        config.COPILOT_MODEL,
        "gpt-4.1", "gpt-4o", "gpt-5",
    ]
    preference_qa = [
        "gpt-4.1-mini", "gpt-4o-mini", "gpt-5-mini",
        config.COPILOT_MODEL, "gpt-4.1", "gpt-4o",
    ]
    pref = preference_qa if agent_type == "qa" else preference_main
    for candidate in pref:
        if candidate and candidate in available:
            return candidate
    return available[0]


def _approx_tokens(blocks: list[dict]) -> int:
    total = 600  # framing
    for b in blocks:
        total += len((b.get("content") or "")) // 4
        for it in (b.get("items") or []):
            if it.get("selected"):
                total += len(it.get("label", "")) // 4
    return total


def decide(
    *,
    agent_type: str,
    blocks: list[dict],
    fingerprint_complexity: str | None = None,
    override: str | None = None,
    backend: str | None = None,
    project_name: str | None = None,
) -> RoutingDecision:
    """Devuelve qué modelo usar y por qué."""
    backend = (backend or config.LLM_BACKEND or "anthropic").lower()

    # Para vscode_bridge: verificar que el bridge esté activo antes de routear,
    # usando el puerto del proyecto si está disponible.
    if backend == "vscode_bridge":
        from copilot_bridge import _vscode_bridge_health
        from services.vscode_instance_manager import get_instance_info

        bridge_port: int | None = None
        port_origin = "global"
        if project_name:
            info = get_instance_info(project_name)
            if info and isinstance(info.get("port"), int):
                bridge_port = info["port"]
                port_origin = f"proyecto '{project_name}'"

        if not _vscode_bridge_health(project_name=project_name, bridge_port=bridge_port):
            port_label = f":{bridge_port}" if bridge_port else f":{config.VSCODE_BRIDGE_PORT} (global fallback)"
            raise RuntimeError(
                f"El bridge de VS Code no responde en {port_label} (origen: {port_origin}). "
                "Recargá VS Code: Ctrl+Shift+P → 'Developer: Reload Window'"
            )

    available = _available_models()

    if backend == "mock":
        return RoutingDecision(model="mock-1.0", reason="LLM_BACKEND=mock")

    if override:
        capped = clamp_model(override)
        if capped != override:
            # Override prohibido (opus/fable): se respeta la intención de forzar
            # modelo pero clampeado al tope permitido (§5.2).
            return RoutingDecision(
                model=capped,
                reason=f"user-override {override} -> clamp §5.2 ({capped})",
            )
        if override in available:
            return RoutingDecision(model=override, reason="user-override")

    tokens = _approx_tokens(blocks)

    if backend in ("copilot", "vscode_bridge"):
        default = _pick_copilot_default(agent_type, available)
        # Reglas de upgrade para Copilot — chequeamos disponibilidad antes de elegir.
        if (fingerprint_complexity == "XL" or tokens > 30_000) and "o3" in available:
            return RoutingDecision(
                model="o3",
                reason=(
                    "complexity=XL (fingerprint)"
                    if fingerprint_complexity == "XL"
                    else f"contexto grande ({tokens} tok > 30k)"
                ),
            )
        if agent_type == "qa" and tokens < 6_000 and "gpt-4.1-mini" in available:
            return RoutingDecision(model="gpt-4.1-mini", reason="qa rápido (qa + <6k tok)")
        if agent_type == "qa" and tokens < 6_000 and "gpt-4o-mini" in available:
            return RoutingDecision(model="gpt-4o-mini", reason="qa rápido (qa + <6k tok)")
        return RoutingDecision(model=default, reason="default por agente (copilot)")

    # Claude / anthropic — §5.2: cap duro en sonnet-4-6, jamás opus/fable.
    # "Complejo" = sonnet (antes opus); "simple" = haiku; default seguro = sonnet.
    default = DEFAULT_BY_AGENT_CLAUDE.get(agent_type, "claude-sonnet-4-6")
    if fingerprint_complexity == "XL":
        decision = RoutingDecision(model="claude-sonnet-4-6", reason="complexity=XL (fingerprint) -> sonnet (cap §5.2)")
    elif tokens > 30_000:
        decision = RoutingDecision(model="claude-sonnet-4-6", reason=f"contexto grande ({tokens} tok > 30k) -> sonnet (cap §5.2)")
    elif agent_type == "developer" and tokens > 12_000:
        decision = RoutingDecision(model="claude-sonnet-4-6", reason=f"developer + contexto {tokens} tok > 12k -> sonnet (cap §5.2)")
    elif agent_type == "qa" and tokens < 6_000:
        decision = RoutingDecision(model="claude-haiku-4-5", reason="qa rápido (qa + <6k tok)")
    elif agent_type == "functional" and tokens < 3_000:
        decision = RoutingDecision(model="claude-haiku-4-5", reason="functional simple (<3k tok)")
    else:
        decision = RoutingDecision(model=default, reason="default por agente")
    # Última línea de defensa: clamp sobre TODA decisión Claude (§5.2).
    decision.model = clamp_model(decision.model)
    return decision
