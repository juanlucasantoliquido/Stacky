import os
from pathlib import Path
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent
load_dotenv(BACKEND_ROOT / ".env")


class Config:
    PORT = int(os.getenv("PORT", "5050"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    DATABASE_URL = os.getenv(
        "DATABASE_URL", f"sqlite:///{BACKEND_ROOT / 'data' / 'stacky_agents.db'}"
    )

    ALLOWED_ORIGINS = [
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]

    LLM_BACKEND = os.getenv("LLM_BACKEND", "vscode_bridge")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4.5")

    # Copilot Chat API
    COPILOT_MODEL = os.getenv("COPILOT_MODEL", "gpt-4.1")
    # GitHub Models API acepta el gho_ token directamente como Bearer.
    # api.githubcopilot.com/chat/completions requiere un internal token que
    # solo se puede obtener via OAuth app de VS Code (no via gh CLI).
    COPILOT_ENDPOINT = os.getenv(
        "COPILOT_ENDPOINT", "https://models.inference.ai.azure.com/chat/completions"
    )
    # Catalog de modelos disponibles (short IDs que acepta el inference endpoint)
    COPILOT_MODELS_ENDPOINT = os.getenv(
        "COPILOT_MODELS_ENDPOINT", "https://models.github.ai/catalog/models"
    )
    COPILOT_INTEGRATION_ID = os.getenv("COPILOT_INTEGRATION_ID", "vscode-chat")

    # Puerto del bridge HTTP de la extensión VS Code
    VSCODE_BRIDGE_PORT = int(os.getenv("VSCODE_BRIDGE_PORT", "5052"))
    VSCODE_PROMPTS_DIR = os.getenv(
        "VSCODE_PROMPTS_DIR",
        str(Path.home() / "AppData" / "Roaming" / "Code" / "User" / "prompts"),
    )

    ADO_ORG = os.getenv("ADO_ORG", "")
    ADO_PROJECT = os.getenv("ADO_PROJECT", "")
    ADO_PAT = os.getenv("ADO_PAT", "")

    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"


config = Config()
