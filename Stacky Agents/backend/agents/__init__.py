from .base import BaseAgent
from .business import BusinessAgent
from .custom import CustomAgent
from .debug import DebugAgent, PRReviewAgent
from .developer import DeveloperAgent
from .devops import DevOpsAgent
from .functional import FunctionalAgent
from .qa import QAAgent
from .technical import TechnicalAgent

registry: dict[str, BaseAgent] = {
    a.type: a
    for a in [
        BusinessAgent(),
        FunctionalAgent(),
        TechnicalAgent(),
        DeveloperAgent(),
        DevOpsAgent(),      # Plan 90 — agente DevOps conversacional
        QAAgent(),
        DebugAgent(),       # FA-29
        PRReviewAgent(),    # FA-28
        CustomAgent(),      # VS Code / Copilot custom agents
    ]
}


def list_agents() -> list[dict]:
    return [a.describe() for a in registry.values()]


def get(agent_type: str) -> BaseAgent | None:
    return registry.get(agent_type)
