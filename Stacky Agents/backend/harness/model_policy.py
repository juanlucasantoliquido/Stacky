"""H2.4 — Política de modelo por runtime.

resolve_model(runtime, requested) -> (model, reason)

  - "claude_code_cli": aplica llm_router.clamp_model (cap vinculante, nunca Opus/Fable).
  - "codex_cli": passthrough de requested/CODEX_CLI_MODEL; si el modelo matchea
    CODEX_CLI_MODEL_DENYLIST (CSV), degrada a CODEX_CLI_MODEL y registra reason.
  - otros runtimes: passthrough sin restricciones.

El caller debe persistir (model, reason) en metadata["model_decision"].
"""
from __future__ import annotations


def resolve_model(runtime: str, requested: str | None) -> tuple[str | None, str]:
    """Devuelve (model_final, reason).

    model_final puede ser None si no hay modelo configurado ni requesteado
    (en ese caso el runtime usa su default).
    """
    from config import config

    if runtime == "claude_code_cli":
        from services.llm_router import clamp_model
        clamped = clamp_model(requested or config.CLAUDE_CODE_CLI_MODEL or None)
        if clamped != requested:
            reason = f"clamped from {requested!r} to {clamped!r} (cap §5.2)"
        else:
            reason = "passthrough (dentro del cap)"
        return clamped, reason

    if runtime == "codex_cli":
        denylist_raw = (getattr(config, "CODEX_CLI_MODEL_DENYLIST", "") or "").strip()
        denylist = {m.strip().lower() for m in denylist_raw.split(",") if m.strip()}

        model = requested or config.CODEX_CLI_MODEL or None

        if model and denylist and model.lower() in denylist:
            fallback = config.CODEX_CLI_MODEL or None
            reason = (
                f"modelo {model!r} está en CODEX_CLI_MODEL_DENYLIST; "
                f"degradado a config.CODEX_CLI_MODEL={fallback!r}"
            )
            return fallback, reason

        return model, "passthrough"

    # Otros runtimes: sin política
    model = requested
    return model, "passthrough (runtime sin política)"
