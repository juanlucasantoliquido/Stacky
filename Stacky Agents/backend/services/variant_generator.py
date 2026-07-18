"""Plan 169 F2 — Generador de variantes del optimizador evolutivo.

Una función única `generate(...)` produce el texto de una variante vía el modelo LOCAL
(`invoke_local_llm`, USD 0) o vía el RUNTIME de agentes (Codex/Claude/Copilot) con el
patrón one-shot del Documentador (ticket sentinela `-9` + espera + parse de marcadores).
Fallback declarado por combinación (tabla §F2). NINGÚN camino nuevo de invocación: todo
delega en `agent_runner.run_agent` o `copilot_bridge.invoke_local_llm`.

Juez ≠ generador (§3.5): el modelo del generador SIEMPRE se declara (`generator_model_for`)
para que el 168 aplique bien `SELF_JUDGE_MULTIPLIER` (modo local) o nunca marque
self_judge espurio (modo runtime → `runtime:<r>`, jamás coincide con el juez local).
"""
from __future__ import annotations

import json
from pathlib import Path

import runtime_paths
from config import config as _cfg  # G1

# ── Literal del system prompt del mutador (§4.5, CONGELADO) ───────────────────
_MUTATOR_SYSTEM = (
    "Sos el MUTADOR del optimizador evolutivo de Stacky. Recibis un ARTEFACTO DE TEXTO "
    "(el prompt de sistema de un agente), las CRITICAS de su ultima evaluacion (por que "
    "fallo cada caso), LECCIONES de mutaciones previas y opcionalmente PADRES (variantes "
    "prometedoras anteriores). Tu unica tarea es producir UNA variante COMPLETA y "
    "mejorada del artefacto que ataque especificamente las criticas, conservando todo "
    "lo que ya funciona (rol, contrato de salida, limites). PROHIBIDO: acortar el "
    "artefacto a menos de la mitad, cambiar el idioma, inventar herramientas o "
    "capacidades, eliminar rieles de seguridad o de supervision del operador. Responde "
    "EXACTAMENTE con este formato:\n"
    "<<<VARIANTE>>>\n{artefacto completo}\n<<<FIN_VARIANTE>>>\n"
    "<<<LECCION>>>\n{1-3 lineas: que cambiaste y por que deberia mejorar el score}\n"
    "<<<FIN_LECCION>>>\n"
    "Opcional: si detectas que conviene OTRO valor para una flag de modelo local, "
    "agrega ademas este bloque (una sola vez):\n"
    "<<<SUGERENCIA_FLAG>>>\n{\"flag\": \"...\", \"value\": \"...\", \"razon\": \"...\"}\n"
    "<<<FIN_SUGERENCIA_FLAG>>>\n"
    "Nada mas que esos bloques."
)

_OPTIMIZER_ADO_ID = -9
_GENERATE_TIMEOUT_S = 1800  # mismo anti-zombie que doc_documenter.py:171
VALID_RUNTIMES = ("github_copilot", "claude_code_cli", "codex_cli")
_AGENT_FILENAME = "EvolutionMutator.agent.md"

# Template embebido (deploy frozen, G15): si el repo no trae el .agent.md, se materializa esto.
_AGENT_TEMPLATE_MD = (
    "---\n"
    "name: EvolutionMutator\n"
    "description: Genera variantes mejoradas de un artefacto de texto para el optimizador evolutivo\n"
    "tools: []\n"
    "---\n\n"
    + _MUTATOR_SYSTEM
    + "\n"
)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def extract_block(text: str, start_marker: str, end_marker: str) -> str | None:
    """Primer start_marker y el PRIMER end_marker posterior; strip(); sin par → None."""
    if not text:
        return None
    si = text.find(start_marker)
    if si == -1:
        return None
    content_start = si + len(start_marker)
    ei = text.find(end_marker, content_start)
    if ei == -1:
        return None
    return text[content_start:ei].strip()


def resolve_generator_mode() -> tuple[str, bool]:
    """(mode, ready). auto = local si hay LOCAL_LLM_ENDPOINT, si no runtime."""
    flag = str(getattr(_cfg, "STACKY_EVOLUTION_OPTIMIZER_GENERATOR", "auto") or "auto").strip().lower()
    endpoint_ready = bool(getattr(_cfg, "LOCAL_LLM_ENDPOINT", ""))
    if flag == "local":
        return ("local", endpoint_ready)
    if flag == "runtime":
        return ("runtime", True)
    # auto / cualquier otro valor
    if endpoint_ready:
        return ("local", True)
    return ("runtime", True)


def generator_model_for(mode: str, runtime: str | None) -> str:
    if mode == "local":
        return str(getattr(_cfg, "LOCAL_LLM_MODEL", "") or "local")
    return f"runtime:{runtime}"


def ensure_evolution_mutator_agent_file() -> Path:
    """Espejo EXACTO de incident_dev_context.ensure_incident_dev_agent_file (:97-118).
    Existe → NO tocar; si no, copiar del repo; deploy frozen → template embebido."""
    dest = runtime_paths.stacky_agents_dir() / _AGENT_FILENAME
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    repo_template = Path(__file__).resolve().parents[1] / "agents" / _AGENT_FILENAME
    try:
        content = repo_template.read_text(encoding="utf-8")
    except OSError:
        content = _AGENT_TEMPLATE_MD
    dest.write_text(content, encoding="utf-8", newline="")
    return dest


def _ensure_optimizer_ticket() -> int:
    """Espejo EXACTO de doc_documenter._ensure_documenter_ticket (:307-334): ticket
    sentinela con ado_id=-9 discriminador + external_id=-ticket.id único negativo.
    Reusa el ticket existente. ABRE SESIÓN DE DB REAL — en tests SIEMPRE mockeado (C8/G14)."""
    from db import session_scope
    from models import Ticket
    project = "stacky-evolution"
    with session_scope() as session:
        existing = (session.query(Ticket)
                    .filter_by(ado_id=_OPTIMIZER_ADO_ID, stacky_project_name=project)
                    .order_by(Ticket.id).first())
        if existing is not None:
            return existing.id
        ticket = Ticket(
            ado_id=_OPTIMIZER_ADO_ID,
            project=project,
            stacky_project_name=project,
            title="[Optimizador] mutacion de artefactos",
            work_item_type="Task",
            ado_state="Active",
        )
        session.add(ticket)
        session.flush()
        ticket.external_id = -ticket.id
        session.flush()
        return ticket.id


def _wait_and_read_output(execution_id: int, timeout_s: int = _GENERATE_TIMEOUT_S) -> str:
    """Espejo EXACTO de doc_documenter._wait_and_read_output (:337-361): poll 1.0 s de
    AgentExecution.status hasta terminal o timeout. Devuelve output ("" si vacío/timeout).
    Nunca crashea."""
    import time
    from db import session_scope
    from models import AgentExecution
    deadline = time.time() + max(1, timeout_s)
    terminal = {"completed", "failed", "cancelled", "error"}
    while time.time() < deadline:
        try:
            with session_scope() as s:
                ex = s.get(AgentExecution, execution_id)
                status = (ex.status if ex else "") or ""
                output = (ex.output if ex else "") or ""
            if status in terminal:
                return output
        except Exception:  # noqa: BLE001
            return ""
        time.sleep(1.0)
    return ""


def generate(*, user_prompt: str, mode: str, runtime: str | None, on_step=None) -> dict:
    """Devuelve SIEMPRE el dict del contrato §F2."""
    result: dict = {
        "text": None, "lesson": None, "flag_suggestion": None,
        "model": generator_model_for(mode, runtime),
        "tokens_est_in": _estimate_tokens(user_prompt), "tokens_est_out": 0, "error": None,
    }

    if mode == "local":
        from copilot_bridge import invoke_local_llm  # import LAZY
        try:
            resp = invoke_local_llm(
                agent_type="evolution_mutator", system=_MUTATOR_SYSTEM,
                user=user_prompt, on_log=lambda level, msg: None,
                execution_id=None, model=None,
            )
        except RuntimeError as exc:  # degradación declarada (endpoint caído)
            result["error"] = str(exc)
            return result
        raw = resp.text
    elif mode == "runtime":
        ensure_evolution_mutator_agent_file()
        import agent_runner
        try:
            execution_id = agent_runner.run_agent(
                agent_type="evolution_mutator",
                ticket_id=_ensure_optimizer_ticket(),
                context_blocks=[{
                    "id": "mutation", "kind": "raw-conversation",
                    "title": "Pedido de mutacion", "content": user_prompt,
                    "source": {"type": "evolution_optimizer"},
                }],
                user="optimizer", runtime=runtime,
                vscode_agent_filename=_AGENT_FILENAME,
                system_prompt_override=_MUTATOR_SYSTEM,
                use_few_shot=False, use_anti_patterns=False, work_item_type="Task",
            )
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"runtime_launch_failed: {exc}"
            return result
        raw = _wait_and_read_output(execution_id)
        if not raw:
            result["error"] = "runtime_sin_output"
            return result
    else:
        result["error"] = f"modo_invalido: {mode}"
        return result

    result["tokens_est_out"] = _estimate_tokens(raw or "")
    text = extract_block(raw, "<<<VARIANTE>>>", "<<<FIN_VARIANTE>>>")
    if text is None:
        result["error"] = "sin_marcador_variante"
        return result
    result["text"] = text
    result["lesson"] = extract_block(raw, "<<<LECCION>>>", "<<<FIN_LECCION>>>")
    flag_block = extract_block(raw, "<<<SUGERENCIA_FLAG>>>", "<<<FIN_SUGERENCIA_FLAG>>>")
    if flag_block:
        try:
            parsed = json.loads(flag_block)
            if isinstance(parsed, dict):
                result["flag_suggestion"] = parsed
        except Exception:  # noqa: BLE001 — JSON roto → None
            result["flag_suggestion"] = None
    return result
