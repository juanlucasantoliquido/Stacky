"""
speculative_executor.py — PM corre en background mientras el ticket está en cola.

Cuando Stacky detecta tickets en cola, lanza PM en background especulativamente.
Cuando el ticket entra al pipeline real, el análisis ya está listo → latencia PM = 0.

Uso:
    from speculative_executor import SpeculativeExecutor
    executor = SpeculativeExecutor(config)
    executor.run_speculative_pm(ticket_queue)
    result = executor.consume_speculation(ticket_id)
"""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.speculative")


class SpeculativeExecutor:
    SPECULATION_LOOKAHEAD = 3
    SPEC_DIR_SUFFIX = "_speculative"

    def __init__(self, config: Optional[dict] = None, copilot_bridge=None):
        self.config = config or {}
        self.copilot_bridge = copilot_bridge
        self._active_threads: dict[str, threading.Thread] = {}
        self._results: dict[str, str] = {}  # ticket_id → spec_folder

    def run_speculative_pm(self, ticket_queue: list[dict]):
        for ticket in ticket_queue[:self.SPECULATION_LOOKAHEAD]:
            ticket_id = str(ticket.get("id", ""))
            if not ticket_id:
                continue
            if ticket_id in self._results:
                logger.debug("[Speculative] Already available for #%s", ticket_id)
                continue
            if ticket_id in self._active_threads:
                logger.debug("[Speculative] Already running for #%s", ticket_id)
                continue

            thread = threading.Thread(
                target=self._run_pm_background,
                args=(ticket,),
                daemon=True,
                name=f"speculative-pm-{ticket_id}"
            )
            self._active_threads[ticket_id] = thread
            thread.start()
            logger.info("[Speculative] PM launched in background for #%s", ticket_id)

    def consume_speculation(self, ticket_id: str) -> Optional[str]:
        ticket_id = str(ticket_id)
        if ticket_id not in self._results:
            return None

        spec_folder = self._results[ticket_id]
        if not Path(spec_folder).exists():
            del self._results[ticket_id]
            return None

        if self._is_speculation_valid(ticket_id, spec_folder):
            logger.info("[Speculative] Consuming pre-computed PM for #%s", ticket_id)
            del self._results[ticket_id]
            return spec_folder

        logger.info("[Speculative] Discarding stale speculation for #%s", ticket_id)
        shutil.rmtree(spec_folder, ignore_errors=True)
        del self._results[ticket_id]
        return None

    def has_speculation(self, ticket_id: str) -> bool:
        return str(ticket_id) in self._results

    def _run_pm_background(self, ticket: dict):
        ticket_id = str(ticket.get("id", ""))
        try:
            spec_folder = self._create_spec_folder(ticket)
            if not spec_folder:
                return

            # Build minimal PM prompt from ticket description
            from prompt_builder import build_pm_prompt
            inc_path = Path(spec_folder)
            inc_files = list(inc_path.glob("INC-*.md")) + list(inc_path.glob("INC_*.md"))
            if not inc_files:
                (inc_path / f"INC-{ticket_id}.md").write_text(
                    f"# Ticket #{ticket_id}\n{ticket.get('description', 'N/A')}",
                    encoding="utf-8"
                )

            prompt = build_pm_prompt(
                spec_folder, ticket_id,
                self.config.get("project_name", "RSPACIFICO"),
            )

            if self.copilot_bridge:
                self.copilot_bridge.invoke_agent(
                    prompt,
                    agent_name=self.config.get("agents", {}).get("pm", "PM-TLStack1"),
                    project_name=self.config.get("project_name", ""),
                )

            self._results[ticket_id] = spec_folder
            logger.info("[Speculative] PM completed for #%s", ticket_id)
        except Exception as e:
            logger.error("[Speculative] PM failed for #%s: %s", ticket_id, e)
        finally:
            self._active_threads.pop(ticket_id, None)

    def _create_spec_folder(self, ticket: dict) -> Optional[str]:
        ticket_id = str(ticket.get("id", ""))
        base = Path(self.config.get("speculation_dir",
                                     str(Path(__file__).parent / "state" / "speculative")))
        spec_folder = base / ticket_id
        spec_folder.mkdir(parents=True, exist_ok=True)
        return str(spec_folder)

    def _is_speculation_valid(self, ticket_id: str, spec_folder: str) -> bool:
        folder = Path(spec_folder)
        required = ["ANALISIS_TECNICO.md", "ARQUITECTURA_SOLUCION.md"]
        return all((folder / f).exists() for f in required)
