"""V0.4 — Taxonomía de fallos del arnés.

Clasifica un run terminado en una causa agregable. PURO: no toca disco ni DB.

KINDS y reglas deterministas (en orden de prioridad):
  1. metadata["runaway"] presente            → "runaway"
  2. cancelación explícita (metadata/flag)    → "cancelled"
  3. mensaje de timeout de sesión             → "timeout"
  4. fallo de spawn (sin PID / FileNotFound)  → "spawn_error"
  5. contract_result passed=False + needs_review → "contract_failed"
  6. resto con return_code != 0               → "crash"
  7. ninguno aplica (run ok)                  → None

Clave NUEVA de metadata: "failure_kind". Nunca renombra claves existentes.
"""
from __future__ import annotations

KINDS = (
    "spawn_error",
    "timeout",
    "runaway",
    "contract_failed",
    "cancelled",
    "crash",
)

_TIMEOUT_MARKERS = ("timeout", "timed out", "tiempo de espera", "deadline exceeded")
_SPAWN_MARKERS = (
    "filenotfounderror",
    "no such file",
    "not found",
    "cannot find the file",
    "failed to spawn",
    "could not start",
    "no se encontr",
)


def classify(
    *,
    return_code: int | None,
    error_message: str | None,
    metadata: dict,
) -> str | None:
    """Devuelve el failure_kind de un run terminado, o None si fue ok.

    Args:
        return_code: código de retorno del subproceso CLI (None si no spawneó).
        error_message: mensaje de error libre (puede ser None).
        metadata: dict de metadata del run (lectura: runaway, cancelled,
            contract_result, status, spawn_failed).
    """
    md = metadata or {}
    msg = (error_message or "").lower()

    # 1. Runaway: el guard cortó el run.
    if md.get("runaway") is not None:
        return "runaway"

    # 2. Cancelación explícita.
    if md.get("cancelled") is True or md.get("cancelled_by") is not None:
        return "cancelled"
    if "cancel" in msg and return_code != 0:
        return "cancelled"

    # 3. Timeout de sesión.
    if any(m in msg for m in _TIMEOUT_MARKERS):
        return "timeout"

    # 4. Fallo de spawn: nunca arrancó el proceso.
    if md.get("spawn_failed") is True:
        return "spawn_error"
    if return_code is None and any(m in msg for m in _SPAWN_MARKERS):
        return "spawn_error"

    # 5. Contrato fallido → needs_review.
    cr = md.get("contract_result") or {}
    status = md.get("status")
    if cr.get("passed") is False and status == "needs_review":
        return "contract_failed"

    # 6. Crash genérico: terminó con código != 0.
    if return_code is not None and return_code != 0:
        return "crash"
    if return_code is None and msg:
        # Hubo un error reportado pero no encaja en spawn/timeout: crash.
        return "crash"

    # 7. Run ok.
    return None
