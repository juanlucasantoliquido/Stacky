"""services/error_analysis.py — Plan 127 C1. Núcleo puro del análisis de errores.

Prompt determinista desde el snapshot forense de api.diag (Plan 127 F1).
Sin Flask, sin red, sin ORM. La llamada al LLM vive en api/local_llm_analysis.py.
"""
from __future__ import annotations

import json

from services.local_insights import HITL_RULES, truncate_middle   # puros, solo lectura
from services.pr_review_sanitize import redact_secrets            # Plan 110

ERROR_ANALYSIS_KEY = "error_analysis"   # key en AgentExecution.metadata_json
ANALYSIS_MAX = 4000                     # cap del markdown persistido
OUTPUT_HEAD_CHARS = 3000
OUTPUT_TAIL_CHARS = 3000
RECOVERY_HISTORY_MAX = 10               # últimas N transiciones al prompt
ANALYZABLE_STATUSES = frozenset({"error", "needs_review"})


def is_analyzable(status: str, error_message: str) -> bool:
    """True si status ∈ ANALYZABLE_STATUSES o hay error_message no vacío.

    DECISIÓN EXPLÍCITA (v2, H7): "running" NO es analizable — el análisis es
    post-mortem sobre runs TERMINADOS. Un run colgado/zombie se diagnostica con el
    snapshot determinista de diag (stale-running) y el flujo de recovery existente;
    analizarlo con el LLM daría conclusiones sobre un output parcial. Un run
    "running" sin error_message devuelve False ⇒ la API responde 409.
    """
    if status in ANALYZABLE_STATUSES:
        return True
    return bool(error_message and error_message.strip())


def build_error_analysis_prompt(snapshot: dict, output_text: str) -> tuple[str, str]:
    """(system, user). El user se pasa ÍNTEGRO por redact_secrets al final."""
    system = (
        "Sos un ingeniero senior de debugging de sistemas de agentes IA. "
        "Tu ÚNICA tarea es analizar el fallo de una ejecución y explicarlo en markdown."
        + HITL_RULES
    )

    execution = (snapshot or {}).get("execution") or {}
    diagnosis = (snapshot or {}).get("diagnosis")
    recommended_action = (snapshot or {}).get("recommended_action")
    heartbeat = (snapshot or {}).get("heartbeat")
    manifest = (snapshot or {}).get("manifest")
    recovery_history = (snapshot or {}).get("recovery_history") or []

    parts: list[str] = []

    parts.append("== EJECUCIÓN ==")
    parts.append(f"id: {execution.get('id')}")
    parts.append(f"agent_type: {execution.get('agent_type')}")
    parts.append(f"status: {execution.get('status')}")
    parts.append(f"started_by: {execution.get('started_by')}")
    parts.append(f"started_at: {execution.get('started_at')}")
    parts.append(f"completed_at: {execution.get('completed_at')}")
    parts.append(f"completion_source: {execution.get('completion_source')}")

    parts.append("\n== ERROR ==")
    parts.append(str(execution.get("error_message")))

    parts.append("\n== DIAGNOSIS DETERMINISTA ==")
    parts.append(f"diagnosis: {diagnosis}")
    parts.append(f"recommended_action: {recommended_action}")

    parts.append("\n== HEARTBEAT ==")
    parts.append(json.dumps(heartbeat, ensure_ascii=False))

    parts.append("\n== MANIFEST ==")
    parts.append(json.dumps(manifest, ensure_ascii=False) if manifest is not None else "(sin manifest)")

    parts.append("\n== TRANSICIONES (últimas 10) ==")
    for ev in recovery_history[-RECOVERY_HISTORY_MAX:]:
        parts.append(
            f"{ev.get('old_status')}→{ev.get('new_status')} "
            f"({ev.get('changed_by')}, {ev.get('changed_at')}): {ev.get('reason')}"
        )

    parts.append("\n== COLA DEL OUTPUT ==")
    parts.append(truncate_middle(output_text, OUTPUT_HEAD_CHARS, OUTPUT_TAIL_CHARS))

    parts.append(
        "\nRespondé en markdown con EXACTAMENTE estas secciones:\n"
        "## Qué pasó\n## Causa raíz más probable\n## Próximos pasos sugeridos (para el operador)\n"
        "Si la evidencia no alcanza, decilo explícitamente en 'Causa raíz'; NO inventes."
    )

    user = "\n".join(parts)
    user = redact_secrets(user)
    return system, user


def cap_analysis(text: str) -> str:
    """Recorta a ANALYSIS_MAX conservando el inicio; agrega '\n... [recortado]' si recortó."""
    text = text or ""
    if len(text) <= ANALYSIS_MAX:
        return text
    return text[:ANALYSIS_MAX] + "\n... [recortado]"
