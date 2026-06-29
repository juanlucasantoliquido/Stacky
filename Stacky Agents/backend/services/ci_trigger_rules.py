"""Plan 72 F0 — Reglas puras de trigger CI.

3 funciones puras sin I/O:
  - validate_trigger_credentials: validación de scopes best-effort no bloqueante (C3').
  - normalize_ref: normalización de ref a (kind, value).
  - should_trigger: idempotencia por (ref, sha) en ventana de tiempo.
"""
from __future__ import annotations

import re
import time

# Scopes mínimos requeridos por tracker para disparar pipelines.
# GitLab: scope "api". ADO: "vso.build_execute".
REQUIRED_SCOPES: dict[str, set[str]] = {
    "gitlab": {"api"},
    "azure_devops": {"vso.build_execute"},
}

# SHA: 7-40 hex lowercase
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def validate_trigger_credentials(
    tracker_type: str,
    scopes: set[str] | None,
) -> tuple[bool, str]:
    """Valida scopes del PAT de forma best-effort no bloqueante.

    Returns (ok, mensaje).
    - Si scopes is None o vacío → no verificable → (True, "scopes no verificables; se valida en runtime").
    - Si scopes conocidos y faltantes → (False, mensaje con los faltantes).
    - Si tracker_type desconocido o scopes suficientes → (True, "ok").
    """
    if not scopes:
        return True, "scopes no verificables; se valida en runtime"
    required = REQUIRED_SCOPES.get(tracker_type, set())
    missing = required - set(scopes)
    if missing:
        return (
            False,
            f"PAT falta scope(s): {','.join(sorted(missing))} (requerido para trigger en {tracker_type})",
        )
    return True, "ok"


def normalize_ref(ref: str) -> tuple[str, str]:
    """Normaliza ref a (kind, value).

    kind ∈ {"branch", "sha", "tag"} es un HINT de telemetría (C8'):
    GitLab resuelve el ref por sí mismo; el caller pasa SIEMPRE value, nunca
    ramifica comportamiento por kind.

    Reglas:
      SHA: ^[0-9a-f]{7,40}$
      tag: comienza con "refs/tags/"
      resto: branch

    Lanza ValueError si ref está vacío o contiene caracteres prohibidos
    (espacios, "..", caracteres de control).
    """
    if not ref:
        raise ValueError("ref no puede estar vacío")
    if " " in ref or "\t" in ref or ".." in ref:
        raise ValueError(f"ref contiene caracteres prohibidos: {ref!r}")
    # Caracteres de control (ASCII < 32)
    if any(ord(c) < 32 for c in ref):
        raise ValueError(f"ref contiene caracteres de control: {ref!r}")

    if _SHA_RE.match(ref):
        return "sha", ref
    if ref.startswith("refs/tags/"):
        tag = ref[len("refs/tags/"):]
        if not tag:
            raise ValueError("ref tags/ sin nombre: {ref!r}")
        return "tag", ref
    return "branch", ref


def should_trigger(
    ref: str,
    sha: str,
    recent_triggers: list[dict],
    window_seconds: int = 60,
) -> tuple[bool, str | None]:
    """Idempotencia: si hay un trigger reciente para (ref, sha) en la ventana, devuelve (False, pipeline_id).

    - recent_triggers: lista de dicts {"ref", "sha", "pipeline_id", "ts"} (ts = epoch segundos).
    - Si sha es vacío, no hay match (no se puede confirmar idempotencia sin sha).
    - Fuera de la ventana → (True, None).
    - PURA: no muta estado.
    """
    now = time.time()
    for entry in recent_triggers:
        if entry.get("ref") != ref:
            continue
        if sha and entry.get("sha") != sha:
            continue
        if sha == "" or not sha:
            # Sin sha no podemos confirmar idempotencia → dispara
            break
        ts = entry.get("ts", 0)
        if now - ts <= window_seconds:
            return False, str(entry.get("pipeline_id", ""))
    return True, None
