"""I1.1 — Auto-reparación del run ante output vacío/malformado.

Diseño:
  - needs_repair(output_text, artifacts) → "empty_output" | "malformed_artifact" | None
    Función pura. Detecta SOLO problemas triviales de formato:
    - output vacío o solo whitespace
    - artefacto .json existente que no parsea o le falta clave estructural

  - attempt_repair(output_text, artifacts, runtime, retries_budget, retries_used,
                   send_fn, enabled, contract_failed=False) → dict | None
    Orquesta UN único reintento. Retorna metadata del repair o None si no aplica.
    NO repara en:
      - flag enabled=False
      - runtime sin soporte de resume (github_copilot)
      - presupuesto agotado (retries_used >= retries_budget)
      - fallo de criterio de contenido (contract_failed=True)

Contratos de metadata (clave nueva, nunca renombrar existentes):
  metadata["run_repair"] = {
      "attempted": True,
      "reason": "empty_output" | "malformed_artifact",
      "recovered": bool,
  }

Sin dependencias nuevas. Sin efectos secundarios (excepto llamar a send_fn).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from harness.capabilities import CAPABILITIES

logger = logging.getLogger("stacky.run_repair")

# Claves estructurales obligatorias en pending-task.json
_PENDING_TASK_REQUIRED_KEYS = frozenset(["status"])

# Mensaje fijo de repair — corto y directo
_REPAIR_MESSAGE = (
    "Tu salida quedó vacía/malformada. "
    "Re-generá SOLO el artefacto, mismo trabajo, formato válido."
)


def needs_repair(output_text: str, artifacts: list[str]) -> str | None:
    """Detecta si el run necesita reparación trivial.

    Args:
        output_text: texto de salida del agente.
        artifacts: lista de rutas de artefactos a verificar.

    Returns:
        "empty_output" si output está vacío/whitespace.
        "malformed_artifact" si algún .json existe pero no parsea o falta clave.
        None si todo parece correcto.
    """
    if not output_text or not output_text.strip():
        return "empty_output"

    for art_path in artifacts:
        reason = _check_artifact(art_path)
        if reason is not None:
            return reason

    return None


def _check_artifact(art_path: str) -> str | None:
    """Retorna "malformed_artifact" si el archivo existe, es .json y está mal formado."""
    path = Path(art_path)
    if not path.exists():
        return None
    if path.suffix.lower() != ".json":
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError, ValueError):
        return "malformed_artifact"
    # Verificar claves estructurales (aplica solo a pending-task.json por ahora)
    if path.name == "pending-task.json":
        if not isinstance(data, dict):
            return "malformed_artifact"
        if not _PENDING_TASK_REQUIRED_KEYS.issubset(data.keys()):
            return "malformed_artifact"
    return None


def attempt_repair(
    *,
    output_text: str,
    artifacts: list[str],
    runtime: str,
    retries_budget: int,
    retries_used: int,
    send_fn: Callable[[str], str] | None,
    enabled: bool,
    contract_failed: bool = False,
) -> dict | None:
    """Intenta reparar el run ante output vacío/malformado.

    Args:
        output_text: texto de salida actual del agente.
        artifacts: lista de rutas de artefactos.
        runtime: identificador del runtime ("claude_code_cli" | "codex_cli" | ...).
        retries_budget: techo de reintentos del autocorrect del runtime.
        retries_used: reintentos ya consumidos por el autocorrect.
        send_fn: callable(message) → str (nueva salida) o "" si falló.
                 None si el transporte no está disponible.
        enabled: valor del flag STACKY_RUN_REPAIR_ENABLED.
        contract_failed: True si el fallo es de criterio de contenido (no reparar).

    Returns:
        Dict con {attempted, reason, recovered} si se intentó la reparación.
        None si no aplica (flag OFF, runtime sin resume, budget agotado, criterio).
    """
    if not enabled:
        return None

    if contract_failed:
        # Fallo de criterio de contenido: no enmascara mala calidad
        return None

    # Verificar soporte de resume en el runtime
    caps = CAPABILITIES.get(runtime)
    if caps is None or not caps.supports_resume:
        # Declarado explícitamente: github_copilot no repara, sin fallback silencioso
        logger.debug("run_repair: runtime %r sin soporte de resume, skip", runtime)
        return None

    # Presupuesto compartido con el autocorrect del runtime
    if retries_used >= retries_budget:
        logger.debug("run_repair: presupuesto agotado (%d/%d), skip", retries_used, retries_budget)
        return None

    reason = needs_repair(output_text, artifacts)
    if reason is None:
        return None

    if send_fn is None:
        logger.warning("run_repair: needs_repair=%r pero send_fn es None, skip", reason)
        return None

    logger.info("run_repair: intentando reparación (reason=%r, runtime=%r)", reason, runtime)
    try:
        new_output = send_fn(_REPAIR_MESSAGE)
    except Exception as exc:  # noqa: BLE001 — la reparación nunca tumba el run
        logger.warning("run_repair: send_fn lanzó excepción: %s", exc)
        new_output = ""

    recovered = bool(new_output and new_output.strip())
    return {
        "attempted": True,
        "reason": reason,
        "recovered": recovered,
    }
