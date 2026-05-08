"""
FA-49 — Parallel exploration.

Lanza N ejecuciones del mismo agente con el mismo contexto pero distintos
modelos / temperaturas. El operador compara lado a lado y elige la mejor.

FA-48 — Multi-step prompt refinement.

Lanza una cadena de N pasos sobre el mismo agente: cada paso recibe el
output del anterior con un prompt de refinamiento. Útil para:
- "primero analizá", "ahora critica tu propio análisis", "ahora refiná"

Ambas operaciones reusan `agent_runner.run_agent` y devuelven los exec_ids
para que el frontend pueda streamear cada uno.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import agent_runner


@dataclass
class ParallelRun:
    execution_ids: list[int]
    variants: list[dict]          # [{model, temperature, label}, ...]

    def to_dict(self) -> dict:
        return {
            "execution_ids": self.execution_ids,
            "variants": self.variants,
        }


def parallel_explore(
    *,
    agent_type: str,
    ticket_id: int,
    context_blocks: list[dict],
    user: str,
    variants: list[dict] | None = None,
) -> ParallelRun:
    """
    FA-49 — Lanza N execs en paralelo. Cada variante puede tener model distinto.
    Default: 3 variantes (Haiku/Sonnet/Opus).
    """
    if variants is None:
        variants = [
            {"model": "claude-haiku-4-5", "label": "rápido"},
            {"model": "claude-sonnet-4-6", "label": "balanceado"},
            {"model": "claude-opus-4-7", "label": "exhaustivo"},
        ]

    exec_ids: list[int] = []
    for v in variants:
        eid = agent_runner.run_agent(
            agent_type=agent_type,
            ticket_id=ticket_id,
            context_blocks=context_blocks,
            user=user,
            model_override=v.get("model"),
            use_few_shot=True,
            use_anti_patterns=True,
        )
        exec_ids.append(eid)

    return ParallelRun(execution_ids=exec_ids, variants=variants)


@dataclass
class RefinementChain:
    execution_ids: list[int]
    prompts: list[str]
    final_execution_id: int


REFINEMENT_PROMPTS = {
    "default": [
        "Analizá el contexto exhaustivamente.",
        "Critica tu propio análisis: encontrá 3 puntos débiles o asunciones discutibles.",
        "Refiná tu análisis incorporando las críticas. Devolvé la versión final.",
    ],
    "deep_dive": [
        "Producí un análisis inicial.",
        "Identificá los aspectos más complejos del análisis y profundizá específicamente en ellos.",
        "Sintetizá una versión final balanceada con los detalles del paso 2.",
    ],
    "validate": [
        "Producí tu análisis.",
        "Validá tu análisis contra: documentación, restricciones del proyecto, decisiones previas.",
        "Reescribí incorporando validaciones; marcá explícitamente lo que NO pudiste verificar.",
    ],
}


def chain_refinement(
    *,
    agent_type: str,
    ticket_id: int,
    context_blocks: list[dict],
    user: str,
    template: str = "default",
    custom_prompts: list[str] | None = None,
) -> RefinementChain:
    """
    FA-48 — Encadena N pasos sobre el mismo agente. Cada paso es una exec separada.
    El output del paso N-1 entra como bloque adicional en el paso N.
    """
    prompts = custom_prompts or REFINEMENT_PROMPTS.get(template, REFINEMENT_PROMPTS["default"])
    if not prompts:
        raise ValueError("at least one prompt required")

    exec_ids: list[int] = []
    current_blocks = list(context_blocks)

    # Paso 1: contexto original + primer prompt
    first_prompt_block = {
        "id": "refinement-step-1",
        "kind": "auto",
        "title": "Paso 1/{N} — Instrucción".format(N=len(prompts)),
        "content": prompts[0],
        "source": {"type": "refinement", "step": 1},
    }
    eid = agent_runner.run_agent(
        agent_type=agent_type,
        ticket_id=ticket_id,
        context_blocks=current_blocks + [first_prompt_block],
        user=user,
    )
    exec_ids.append(eid)

    # Disparamos pasos siguientes en background; el frontend ve cada exec por id
    def _fire_subsequent_steps():
        from db import session_scope
        from models import AgentExecution
        N = len(prompts)
        for i, p in enumerate(prompts[1:], start=2):
            # Esperar al exec previo
            prev_id = exec_ids[-1]
            for _ in range(120):
                with session_scope() as session:
                    row = session.get(AgentExecution, prev_id)
                    if row and row.status in {"completed", "error", "cancelled"}:
                        break
                time.sleep(1)

            with session_scope() as session:
                prev_row = session.get(AgentExecution, prev_id)
                prev_output = prev_row.output if prev_row else "(sin output)"

            new_blocks = list(context_blocks) + [
                {
                    "id": f"refinement-prev-{i}",
                    "kind": "auto",
                    "title": f"Paso {i-1} — output anterior",
                    "content": prev_output or "(vacío)",
                    "source": {"type": "refinement", "step": i - 1},
                },
                {
                    "id": f"refinement-step-{i}",
                    "kind": "auto",
                    "title": f"Paso {i}/{N} — Instrucción",
                    "content": p,
                    "source": {"type": "refinement", "step": i},
                },
            ]
            new_eid = agent_runner.run_agent(
                agent_type=agent_type,
                ticket_id=ticket_id,
                context_blocks=new_blocks,
                user=user,
            )
            exec_ids.append(new_eid)

    threading.Thread(target=_fire_subsequent_steps, daemon=True).start()

    return RefinementChain(
        execution_ids=exec_ids,
        prompts=prompts,
        final_execution_id=exec_ids[0],   # el frontend irá rotando hasta el final
    )
