"""api/devops_section_doctor.py — Plan 104 F2 (v4, reconciliado 2026-07-07).
Doctores IA por seccion del panel DevOps. Reusa el cableado de invocacion del
plan 90 (agent_runner.run_agent con agent_type="devops"). Cada seccion define
su propio context_blocks (YAML del pipeline, environment, etc.). El doctor
PROPONE analisis/mejoras en markdown; NUNCA aplica cambios (HITL) -- la
barrera es la instruccion del prompt (_HITL_FIRST_LINE), no ausencia de tool:
los runtimes CLI corren con skip-permissions ON y PUEDEN escribir/commitear.

run_agent exige ticket_id: int OBLIGATORIO -- el doctor crea un Ticket ancla
determinista (ado_id=-3, DISTINTO al -2 del plan 90) e idéntico en patrón al
del plan 90 (incluido el sello external_id = -ticket.id, sin el cual el 2do
doctor del mismo proyecto colisiona en el UNIQUE tras el backfill de init_db).
"""
from __future__ import annotations
from flask import Blueprint, jsonify, request, abort
import config as _config  # módulo top-level, NO `services._config` (no existe)

bp = Blueprint("devops_section_doctor", __name__, url_prefix="/devops/sections")

# ado_id negativo DISTINTO al del plan 90 (_CONVERSATION_ADO_ID = -2) para
# distinguir doctor de chat en el historial.
_DOCTOR_CONVERSATION_ADO_ID = -3

# La barrera HITL NO es ausencia de tool de escritura (los runtimes CLI corren
# con skip-permissions ON y PUEDEN escribir/commitear): es la INSTRUCCION del
# prompt. Por eso va como PRIMERA línea, imperativa, en cada doctor.
_HITL_FIRST_LINE = (
    "REGLA ABSOLUTA (HITL): SOLO analiza y proponé en markdown. NUNCA edites archivos, NUNCA "
    "commitees, NUNCA ejecutes comandos que modifiquen el repo o el pipeline. El operador aplica.\n\n"
)

SECTION_DOCTORS: dict[str, dict[str, str]] = {
    "pipeline": {
        "title": "Doctor de pipeline",
        "instruction": _HITL_FIRST_LINE + (
            "Sos un ingeniero DevOps senior. Analiza el siguiente pipeline (spec + YAML "
            "ADO + GitLab) y proponé mejoras concretas: steps faltantes, orden subóptimo, "
            "riesgos de seguridad, caché de dependencias, paralelismo, artifacts. "
            "Devolvé un informe en markdown con secciones 'Hallazgos' y 'Cambios sugeridos' "
            "(como diffs de los steps a cambiar). NO inventes pasos que no apliquen al stack. "
            "NO modifiques archivos: solo proponé."
        ),
    },
    "environments": {
        "title": "Doctor de environments",
        "instruction": _HITL_FIRST_LINE + (
            "Sos un ingeniero DevOps senior. Analizá la definición de los environments "
            "DevOps del proyecto y proponé mejoras: naming, secretos faltantes, "
            "promoción entre ambientes, drift, validaciones. Devolvé markdown con "
            "'Hallazgos' y 'Cambios sugeridos'. NO apliques cambios."
        ),
    },
    "publications": {
        "title": "Doctor de publicaciones",
        "instruction": _HITL_FIRST_LINE + (
            "Sos un ingeniero DevOps senior. Analizá la spec de publicación (qué se "
            "publica, a dónde, bajo qué conditions) y proponé mejoras: rollback, "
            "idempotencia, versionado, gates de calidad. Devolvé markdown con 'Hallazgos' "
            "y 'Cambios sugeridos'. NO apliques cambios."
        ),
    },
}


@bp.post("/<section_id>/doctor")
def section_doctor_route(section_id: str):
    """Invoca al doctor IA de la seccion. Flag STACKY_DEVOPS_SECTION_DOCTOR_ENABLED."""
    if not getattr(_config.config, "STACKY_DEVOPS_SECTION_DOCTOR_ENABLED", False):
        abort(404)
    if not getattr(_config.config, "STACKY_DEVOPS_AGENT_ENABLED", False):
        # Reusa el gate del plan 90 (sin agente DevOps no hay runtime IA).
        return jsonify({"error": "devops_agent_disabled"}), 404
    spec = SECTION_DOCTORS.get(section_id)
    if spec is None:
        return jsonify({"error": "unknown_section", "section": section_id}), 404

    body = request.get_json(silent=True) or {}
    project = body.get("project")
    runtime = body.get("runtime", "claude_code_cli")
    payload = body.get("payload")  # dict estructurado por seccion
    if not project or not isinstance(payload, dict):
        return jsonify({"error": "project y payload son obligatorios"}), 400
    # Los 3 runtimes son VALIDOS (run_agent los despacha: agent_runner.py:94,219,373).
    # github_copilot NO se rechaza aqui -- el guard del plan 90 que lo rechaza es para
    # CHAT CONVERSACIONAL (devops_chat_requires_cli_runtime), no aplica al doctor.
    if runtime not in ("claude_code_cli", "codex_cli", "github_copilot"):
        return jsonify({"error": "runtime_no_soportado"}), 400

    import json
    # YAML SERVER-SIDE: el frontend NO tiene el YAML renderizado (vive en el estado
    # local de PipelineYamlPreview.tsx, no se sube al padre). El backend lo renderiza
    # desde el `spec` con el patron EXACTO de preview_route (api/pipeline_generator.py).
    # Solo para la seccion pipeline y si el generador esta ON; degrada a null si el
    # spec no valida.
    if section_id == "pipeline" and isinstance(payload.get("spec"), dict) and getattr(
        _config.config, "STACKY_PIPELINE_GENERATOR_ENABLED", False
    ):
        try:
            from services.pipeline_spec import dict_to_spec
            from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml
            _spec_obj = dict_to_spec(payload["spec"])
            payload["yaml_ado"] = to_ado_yaml(_spec_obj)
            payload["yaml_gitlab"] = to_gitlab_yaml(_spec_obj)
        except Exception:
            payload.setdefault("yaml_ado", None)
            payload.setdefault("yaml_gitlab", None)

    # `kind` se OMITE del context_block: es seguro porque los consumidores usan
    # `.get("kind", ...)` con default. El plan 90 SÍ setea kind="raw-conversation"
    # (devops_agent.py) -- omitirlo no rompe, solo hereda el default.
    context_blocks = [{
        "id": f"doctor-{section_id}",
        "title": spec["title"],
        "content": (
            f"{spec['instruction']}\n\n"
            f"== CONTEXTO DE LA SECCION ({section_id}) ==\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        ),
        "source": {"type": "devops_panel", "section": section_id},
    }]

    # run_agent exige ticket_id: int. Patron EXACTO del plan 90: crear un Ticket
    # ancla ANTES de invocar (devops_agent.py). Usamos ado_id=-3 para distinguir
    # doctor de conversacion de chat (-2 del 90). Cada click del doctor crea un
    # Ticket nuevo (idempotente a nivel invocacion: dos clicks = dos conversaciones
    # doctor distintas, sin ancla compartida).
    from db import session_scope
    from models import Ticket
    from api.devops_agent import _current_user  # reuso el helper canonico del 90
    import agent_runner

    try:
        with session_scope() as session:
            # Patrón COMPLETO del plan 90 (devops_agent.py): setear los mismos
            # campos Y sellar external_id = -ticket.id. SIN ese sello, el 2º
            # doctor del MISMO proyecto deja external_id=NULL -> el backfill de
            # init_db (db._backfill_multi_project_ticket_columns) lo rellena con
            # ado_id=-3 -> colisión en el UNIQUE ux_tickets_stacky_tracker_external
            # (stacky_project_name, tracker_type, external_id). Negativo+único
            # -> nunca choca.
            ticket = Ticket(
                title=f"Doctor DevOps · {section_id} · {project}",
                ado_id=_DOCTOR_CONVERSATION_ADO_ID,
                project=project,
                stacky_project_name=project,
                work_item_type="Task",
                ado_state="Active",
            )
            session.add(ticket)
            session.flush()               # asigna ticket.id
            ticket.external_id = -ticket.id  # único, negativo, no-NULL ⇒ backfill lo respeta
            session.flush()
            doctor_ticket_id = ticket.id
            # session_scope commitea en __exit__ ⇒ visible al preflight de run_agent.
    except Exception as exc:
        return jsonify({"ok": False, "error": "anchor_ticket_failed",
                        "message": str(exc)}), 502

    try:
        execution_id = agent_runner.run_agent(
            agent_type="devops",
            ticket_id=doctor_ticket_id,    # int OBLIGATORIO — NO None
            context_blocks=context_blocks,
            user=_current_user(),
            runtime=runtime,
            vscode_agent_filename="DevOpsAgent.agent.md",
            project_name=project,
            use_few_shot=False,
            use_anti_patterns=False,
            work_item_type="Task",
        )
    except agent_runner.UnknownAgentError:
        return jsonify({"ok": False, "error": "devops_agent_not_registered"}), 500
    except Exception as exc:  # patrón run_brief (api/agents.py)
        return jsonify({"ok": False, "error": "agent_launch_failed",
                        "message": str(exc)}), 502

    return jsonify({
        "ok": True,
        "execution_id": execution_id,
        "conversation_id": doctor_ticket_id,   # el frontend lo usa para linkear al panel del 90
        "runtime": runtime,
        "section": section_id,
    })
