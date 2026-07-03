"""V0.1 — Perfiles del arnés (presets de flags).

Activar el arnés es UNA decisión (elegir un perfil), no togglear ~26 flags.

- off:  apaga la unión de claves gestionadas por TODOS los presets.
- safe: solo guardrails (gates de contrato + runaway), sin inyección de contexto.
- full: safe + skills + memoria + resume + MCP + knowledge + advisor + intake.

apply_profile reusa el mecanismo hot-apply existente de harness_flags (setattr en
config + os.environ vía apply_updates), NO inventa otro canal de escritura.

El "universo gestionado" = exactamente las claves listadas en los presets.
Un perfil nunca toca flags fuera de su lista (salvo `off`, que apaga la unión).
"""
from __future__ import annotations

import os

# Valores de "apagado" por tipo, para construir el preset `off`.
_OFF_VALUE = {"bool": "false", "csv": "", "int": "0", "float": "0.0"}

PROFILES: dict[str, dict[str, str]] = {
    "off": {},  # se computa dinámicamente (unión de claves de todos los presets)
    "safe": {
        "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED": "true",
        "CODEX_CLI_CONTRACT_GATE_ENABLED": "true",
        "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED": "true",
        "CODEX_CLI_AUTOCORRECT_ENABLED": "true",
        "STACKY_RUNAWAY_MAX_TURNS": "80",
        "STACKY_RUNAWAY_MAX_COST_USD": "5.0",
        "STACKY_MAX_CONCURRENT_RUNS": "3",
    },
    "full": {
        # --- safe ---
        "CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED": "true",
        "CODEX_CLI_CONTRACT_GATE_ENABLED": "true",
        "CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED": "true",
        "CODEX_CLI_AUTOCORRECT_ENABLED": "true",
        "STACKY_RUNAWAY_MAX_TURNS": "80",
        "STACKY_RUNAWAY_MAX_COST_USD": "5.0",
        "STACKY_MAX_CONCURRENT_RUNS": "3",
        # --- inyección de contexto ---
        "CLAUDE_CODE_CLI_HOOKS_ENABLED": "true",
        "CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED": "true",
        "CLAUDE_CODE_CLI_RESUME_ENABLED": "true",
        "CLAUDE_CODE_CLI_MCP_ENABLED": "true",
        "CODEX_CLI_RESUME_ENABLED": "true",
        "STACKY_CONTEXT_BUDGET_ENABLED": "true",
        "STACKY_MEMORY_INJECTION_ENABLED": "true",
        "STACKY_SKILLS_ENABLED": "true",
        "STACKY_CLI_EGRESS_ENABLED": "true",
        # --- V1.x / V2.x ---
        "STACKY_ARTIFACT_INTAKE_ENABLED": "true",  # V1.3
        "STACKY_RUN_ADVISOR_ENABLED": "true",      # V1.2
        "STACKY_RUN_CACHE_DAYS": "7",              # V2.4 — sugerir reuso (no auto-skip)
        "STACKY_EVAL_GATE_MODE": "warn",           # V2.3 — warn (block es opt-in explícito)
        # STACKY_EVALS_INTERVAL_HOURS se deja en 0: es cadencia que auto-gasta LLM,
        # no un guardrail; el operador la enciende explícitamente.
    },
}


def _managed_keys() -> set[str]:
    """Unión de todas las claves referenciadas por los presets safe/full."""
    keys: set[str] = set()
    for name, preset in PROFILES.items():
        if name == "off":
            continue
        keys.update(preset.keys())
    return keys


def _off_preset() -> dict[str, str]:
    """Computa el preset `off`: apaga cada clave gestionada según su tipo."""
    from services.harness_flags import _REGISTRY_INDEX

    result: dict[str, str] = {}
    for key in _managed_keys():
        spec = _REGISTRY_INDEX.get(key)
        flag_type = spec.type if spec else "bool"
        result[key] = _OFF_VALUE.get(flag_type, "false")
    return result


def _resolved_preset(name: str) -> dict[str, str]:
    if name == "off":
        return _off_preset()
    return dict(PROFILES[name])


def apply_profile(name: str, *, respect_explicit_env: bool = False) -> dict[str, object]:
    """Aplica un perfil. Devuelve {flag: valor_tipado_aplicado}.

    Args:
        name: "off" | "safe" | "full".
        respect_explicit_env: si True (boot), una env var ya definida explícitamente
            por el operador NO se pisa (el perfil solo aplica claves no definidas).

    Raises:
        ValueError: perfil desconocido.
    """
    if name not in PROFILES:
        raise ValueError(
            f"Perfil desconocido: {name!r}. Válidos: {sorted(PROFILES)}"
        )
    from services.harness_flags import apply_updates, _REGISTRY_INDEX
    from config import config

    preset = _resolved_preset(name)
    if respect_explicit_env:
        preset = {k: v for k, v in preset.items() if os.getenv(k) is None}

    typed = apply_updates(preset)

    # Hot-apply (mismo patrón que api/harness_flags.put_harness_flags).
    for key, val in typed.items():
        spec = _REGISTRY_INDEX[key]
        # os.environ siempre (cubre env_only y lecturas en call time).
        if isinstance(val, bool):
            os.environ[key] = "true" if val else "false"
        else:
            os.environ[key] = str(val)
        if not spec.env_only:
            try:
                setattr(config, key, val)
            except (AttributeError, TypeError):
                pass
    return typed


def detect_profile() -> str | None:
    """Devuelve el nombre del perfil si los valores actuales coinciden exactamente.

    None = estado "custom" (no coincide con ningún preset conocido).
    Evalúa off, safe, full en ese orden.
    """
    from services.harness_flags import apply_updates

    # full es superset de safe: probar del más específico al menos específico.
    for name in ("full", "safe", "off"):
        preset = _resolved_preset(name)
        try:
            expected = apply_updates(preset)
        except ValueError:
            continue
        if _matches(expected):
            return name
    return None


def _current_value(key: str) -> object:
    """Valor actual de `key`, misma normalización que usa `_matches()`/`detect_profile()`.

    - key fuera del registry → None (la comparación de valor fallará de forma segura).
    - env_only=True → cast desde os.getenv (mismo `_cast_like` del resto del módulo).
    - env_only=False → getattr(config, key, None).

    Plan 82 F4 — extraído de `_matches()` para que `profile_deltas()` reuse
    exactamente la misma lectura sin duplicar la lógica (evita que ambas divergan).
    """
    from services.harness_flags import _REGISTRY_INDEX
    from config import config

    spec = _REGISTRY_INDEX.get(key)
    if spec is None:
        return None
    if spec.env_only:
        return _cast_like(spec.type, os.getenv(key))
    return getattr(config, key, None)


def _matches(expected: dict[str, object]) -> bool:
    """True si TODAS las claves gestionadas tienen el valor esperado actualmente."""
    from services.harness_flags import _REGISTRY_INDEX

    for key, exp_val in expected.items():
        spec = _REGISTRY_INDEX.get(key)
        if spec is None:
            return False
        if not _value_eq(spec.type, _current_value(key), exp_val):
            return False
    return True


def profile_deltas() -> dict[str, int]:
    """Para cada perfil en PROFILES, cuántas de SUS keys difieren del valor actual.

    Reusa `_current_value()` (misma lectura/normalización que `detect_profile()`)
    y `apply_updates()` para castear el preset esperado exactamente igual que
    `detect_profile()`. Determinista, sin side effects (no escribe nada).
    """
    from services.harness_flags import apply_updates, _REGISTRY_INDEX

    result: dict[str, int] = {}
    for name in PROFILES:
        preset = _resolved_preset(name)
        try:
            expected = apply_updates(preset)
        except ValueError:
            result[name] = len(preset)
            continue
        count = 0
        for key, exp_val in expected.items():
            spec = _REGISTRY_INDEX.get(key)
            if spec is None or not _value_eq(spec.type, _current_value(key), exp_val):
                count += 1
        result[name] = count
    return result


def _cast_like(flag_type: str, raw: str | None):
    if raw is None:
        return {"bool": False, "csv": "", "int": 0, "float": 0.0}.get(flag_type, "")
    if flag_type == "bool":
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if flag_type == "int":
        try:
            return int(str(raw).strip())
        except ValueError:
            return 0
    if flag_type == "float":
        try:
            return float(str(raw).strip())
        except ValueError:
            return 0.0
    return str(raw)


def _value_eq(flag_type: str, a, b) -> bool:
    if flag_type == "float":
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    if flag_type == "int":
        try:
            return int(a) == int(b)
        except (TypeError, ValueError):
            return False
    if flag_type == "bool":
        return bool(a) == bool(b)
    return str(a or "") == str(b or "")
