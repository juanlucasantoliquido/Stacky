from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import copilot_bridge
from prompt_builder import render_blocks, with_project_header


@dataclass
class AgentResult:
    output: str
    output_format: str
    metadata: dict


@dataclass
class RunContext:
    """Datos transversales al Run que afectan armado del prompt y elección de modelo."""
    ticket_id: int | None = None
    project: str | None = None
    model_override: str | None = None
    system_prompt_override: str | None = None  # FA-50
    use_few_shot: bool = True                  # FA-12
    use_anti_patterns: bool = True             # FA-11
    use_decisions: bool = True                 # FA-13
    context_text: str = ""                     # texto unificado del input (para FA-13)
    delta_prefix: str | None = None            # FA-32: prefijo delta para re-ejecuciones
    started_by: str = ""                       # FA-10: email del operador para style memory


class BaseAgent(ABC):
    type: str
    name: str
    description: str
    icon: str = ""
    inputs_hint: list[str] = []
    outputs_hint: list[str] = []
    default_blocks: list[str] = []

    @abstractmethod
    def system_prompt(self) -> str: ...

    def build_prompt(self, context_blocks: list[dict], delta_prefix: str | None = None) -> str:
        body = render_blocks(context_blocks)
        if delta_prefix:
            return with_project_header(delta_prefix + "\n\n" + body, self.type)
        return with_project_header(body, self.type)

    # ------------------------------------------------------------------
    # Composición del system prompt
    # ------------------------------------------------------------------
    def compose_system_prompt(self, run_ctx: RunContext) -> tuple[str, dict]:
        """Devuelve (system_prompt_final, metadata_de_composicion).
        Aplica: FA-50 (override), FA-12 (few-shot), FA-11 (anti-patterns)."""
        if run_ctx.system_prompt_override:
            return run_ctx.system_prompt_override, {
                "system_prompt_source": "override",
                "few_shot_count": 0,
                "anti_patterns_count": 0,
            }

        base = self.system_prompt()
        meta: dict = {"system_prompt_source": "default"}
        prefix_parts: list[str] = []

        if run_ctx.use_few_shot:
            try:
                from services import few_shot

                examples = few_shot.pick_examples(
                    agent_type=self.type,
                    project=run_ctx.project,
                    exclude_ticket_id=run_ctx.ticket_id,
                    k=2,
                )
                if examples:
                    prefix_parts.append(few_shot.build_prefix(examples))
                    meta["few_shot_count"] = len(examples)
                    meta["few_shot_exec_ids"] = [e.execution_id for e in examples]
                else:
                    meta["few_shot_count"] = 0
            except Exception as exc:  # noqa: BLE001
                meta["few_shot_error"] = str(exc)
                meta["few_shot_count"] = 0

        if run_ctx.use_anti_patterns:
            try:
                from services import anti_patterns

                patterns = anti_patterns.relevant(
                    agent_type=self.type, project=run_ctx.project
                )
                if patterns:
                    prefix_parts.append(anti_patterns.build_prefix(patterns))
                    meta["anti_patterns_count"] = len(patterns)
                else:
                    meta["anti_patterns_count"] = 0
            except Exception as exc:  # noqa: BLE001
                meta["anti_patterns_error"] = str(exc)
                meta["anti_patterns_count"] = 0

        if run_ctx.use_decisions:
            try:
                from services import decisions

                decs = decisions.relevant(
                    project=run_ctx.project,
                    context_text=run_ctx.context_text or "",
                )
                if decs:
                    prefix_parts.append(decisions.build_prefix(decs))
                    meta["decisions_count"] = len(decs)
                else:
                    meta["decisions_count"] = 0
            except Exception as exc:  # noqa: BLE001
                meta["decisions_error"] = str(exc)
                meta["decisions_count"] = 0

        # FA-08 — constraints injection (después de decisiones, antes del base prompt)
        try:
            from services import constraints

            clist = constraints.relevant(
                agent_type=self.type,
                project=run_ctx.project,
                context_text=run_ctx.context_text or "",
            )
            if clist:
                prefix_parts.append(constraints.build_prefix(clist))
                meta["constraints_count"] = len(clist)
            else:
                meta["constraints_count"] = 0
        except Exception as exc:  # noqa: BLE001
            meta["constraints_error"] = str(exc)
            meta["constraints_count"] = 0

        # FA-10 — personal style memory
        if run_ctx.started_by:
            try:
                from services import style_memory

                note = style_memory.style_prompt_note(run_ctx.started_by, self.type)
                if note:
                    prefix_parts.append(note)
                    meta["style_memory_active"] = True
                else:
                    meta["style_memory_active"] = False
            except Exception as exc:  # noqa: BLE001
                meta["style_memory_error"] = str(exc)

        if prefix_parts:
            full = "\n\n".join(prefix_parts) + "\n\n# Instrucciones del agente\n\n" + base
        else:
            full = base
        return full, meta

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(
        self,
        context_blocks: list[dict],
        log,
        execution_id: int | None = None,
        run_ctx: RunContext | None = None,
    ) -> AgentResult:
        log("info", f"agent {self.type} start")
        ctx = run_ctx or RunContext()

        system_prompt, sp_meta = self.compose_system_prompt(ctx)
        if sp_meta.get("few_shot_count"):
            log("info", f"few-shot: {sp_meta['few_shot_count']} ejemplos inyectados")
        if sp_meta.get("anti_patterns_count"):
            log("info", f"anti-patterns: {sp_meta['anti_patterns_count']} reglas inyectadas")

        if ctx.delta_prefix:
            log("info", f"FA-32 delta-prompt activo ({len(ctx.delta_prefix)} chars prefix)")
        prompt = self.build_prompt(context_blocks, delta_prefix=ctx.delta_prefix)
        log("debug", f"prompt built ({len(prompt)} chars)")

        response = copilot_bridge.invoke(
            agent_type=self.type,
            system=system_prompt,
            user=prompt,
            on_log=log,
            execution_id=execution_id,
            model=ctx.model_override,
        )
        log("info", f"agent {self.type} done")

        metadata = dict(response.metadata or {})
        metadata.update(sp_meta)
        if ctx.model_override:
            metadata["model_override"] = ctx.model_override
        return AgentResult(
            output=response.text,
            output_format=response.format,
            metadata=metadata,
        )

    def describe(self) -> dict:
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "inputs": self.inputs_hint,
            "outputs": self.outputs_hint,
            "default_blocks": self.default_blocks,
        }
