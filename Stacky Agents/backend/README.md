# Stacky Agents — Backend

Flask 3 + SQLAlchemy 2 + SQLite (dev) / Postgres (prod).

## Quickstart

```bash
cd "Tools/Stacky Agents/backend"
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
python app.py                 # http://localhost:5050  (sincroniza tickets reales desde ADO en arranque)
```

## Variables de entorno

Copiar `.env.example` → `.env` y editar:

```
ADO_ORG=UbimiaPacifico
ADO_PROJECT=Strategist_Pacifico
ADO_PAT=
DATABASE_URL=sqlite:///./data/stacky_agents.db
LLM_BACKEND=mock                         # mock | copilot | claude
LLM_MODEL=claude-sonnet-4-6
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:5173
```

`LLM_BACKEND=mock` devuelve outputs canned y permite probar la UI sin gastar tokens.

## Endpoints principales

Ver [docs/02_ARCHITECTURE.md](../docs/02_ARCHITECTURE.md#api-http--endpoints-completos) para la lista completa.

```
GET  /api/health
GET  /api/agents
POST /api/agents/run
GET  /api/executions?ticket_id=&agent_type=&status=
GET  /api/executions/:id
GET  /api/executions/:id/logs/stream         (SSE)
POST /api/executions/:id/approve
POST /api/executions/:id/discard
POST /api/executions/:id/publish-to-ado
GET  /api/tickets
POST /api/tickets/sync         # trae work items reales desde Azure DevOps
GET  /api/tickets/sync/status  # último sync exitoso
GET  /api/packs
POST /api/packs/start
```

## Estructura

Ver [docs/02_ARCHITECTURE.md](../docs/02_ARCHITECTURE.md#backend--estructura-de-carpetas).

## Tests

```bash
pytest tests/
```
