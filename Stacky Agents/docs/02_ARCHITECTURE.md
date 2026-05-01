# 02 — Arquitectura técnica

## Visión a 30.000 pies

```
┌─────────────────────┐                ┌──────────────────────┐
│   Frontend (React)  │   HTTPS+SSE    │   Backend (Flask)    │
│   Workbench UI      │ ◀────────────▶ │   API + agent_runner │
│   localhost:5173    │                │   localhost:5050     │
└─────────────────────┘                └──────────┬───────────┘
                                                  │
                                ┌─────────────────┼──────────────────┐
                                │                 │                  │
                          ┌─────▼─────┐    ┌──────▼──────┐    ┌─────▼──────┐
                          │  SQLite   │    │  copilot_   │    │  ADO API   │
                          │  agent_   │    │  bridge.py  │    │  (REST)    │
                          │  exec.db  │    │ (delegado)  │    │            │
                          └───────────┘    └──────┬──────┘    └────────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │ VS Code agents │
                                          │ + Stacky tools │
                                          │ existentes     │
                                          └────────────────┘
```

**Tres responsabilidades separadas:**

1. **Frontend** — UX. No tiene lógica de negocio, sólo orquesta llamadas a la API y renderiza.
2. **Backend** — orquestación + persistencia + bridge a los engines reales.
3. **Engines** — los que ya existen en Stacky (copilot bridge, prompt builders, sub-agentes Explore). El backend de Stacky Agents NO los reimplementa — los invoca.

---

## Stack y decisiones

### Backend

| Pieza | Elección | Motivo |
|---|---|---|
| Framework HTTP | **Flask 3.x** | minimal, lo pidió el usuario, conocido por el equipo |
| ORM | **SQLAlchemy 2.x** | maduro, type-safe-ish, soporta SQLite y Postgres |
| BD | **SQLite** (dev) → Postgres (prod) | local-first, file-based, cero ops para empezar |
| Validación | **Pydantic 2** | type-safe parsing en/out, serialización JSON |
| Streaming | **SSE** (server-sent events) | unidireccional, simple, soportado por browsers nativos |
| Tareas largas | **threading + queue** (MVP) → **RQ + Redis** (prod) | empezar simple, escalar cuando duela |
| LLM bridge | `copilot_bridge.py` (delegado a Stacky existente) | no reinventamos |
| Auth | placeholder (header) → Azure AD futuro | el equipo ya tiene contexto Azure |

### Frontend

| Pieza | Elección | Motivo |
|---|---|---|
| Framework | **React 18** | lo pidió el usuario, ecosistema |
| Build tool | **Vite** | rápido, DX moderno |
| Lenguaje | **TypeScript** | catch-bugs-at-compile-time |
| Server state | **TanStack Query** | el estándar para APIs cacheable + invalidate |
| UI state | **Zustand** | liviano, sin boilerplate |
| Estilos | **CSS Modules** + tokens | bundle chico, sin runtime |
| Markdown | **react-markdown** + remark-gfm + rehype-highlight | seguro, customizable |
| Iconos | **lucide-react** | ligero y consistente |
| Diff viewer | **react-diff-viewer-continued** | mantenido, themable |
| SSE | **EventSource** nativo + reconexión propia | sin dependencias |

---

## Backend — estructura de carpetas

```
backend/
├── app.py                  ← entrypoint Flask
├── config.py               ← lee env, default values
├── db.py                   ← engine + Session factory
├── models.py               ← SQLAlchemy models
├── schemas.py              ← Pydantic schemas in/out
├── agent_runner.py         ← núcleo de ejecución
├── prompt_builder.py       ← modular por agente
├── copilot_bridge.py       ← stub que delega al engine real
├── log_streamer.py         ← buffer in-memory + SSE feed
├── api/
│   ├── __init__.py
│   ├── agents.py           ← /api/agents, /api/agents/run, /api/agents/cancel/:id
│   ├── executions.py       ← /api/executions, /api/executions/:id (+logs, +diff, +publish)
│   ├── tickets.py          ← /api/tickets (lectura), /api/tickets/:id
│   └── packs.py            ← /api/packs, /api/packs/start, /api/packs/:id (state machine)
├── agents/
│   ├── __init__.py
│   ├── base.py             ← BaseAgent (contrato)
│   ├── business.py
│   ├── functional.py
│   ├── technical.py
│   ├── developer.py
│   └── qa.py
├── packs/
│   ├── __init__.py
│   └── definitions.py      ← Packs: Desarrollo, QA Express, Discovery
├── data/                   ← SQLite file (gitignored)
└── tests/
    ├── test_agent_runner.py
    ├── test_models.py
    └── test_api_executions.py
```

---

## Contrato `BaseAgent`

```python
# agents/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class AgentResult:
    output: str
    output_format: str        # "markdown" | "json" | "plain"
    metadata: dict            # tokens_used, model, sub_agents, etc.

class BaseAgent(ABC):
    """
    Cada agente concreto declara su tipo, su system prompt base,
    y la función que arma el prompt final a partir del contexto del usuario.
    """
    type: str                 # "business" | "functional" | "technical" | "developer" | "qa"
    name: str
    description: str
    inputs_hint: list[str]    # qué espera (para mostrar en UI)
    outputs_hint: list[str]
    default_blocks: list[str] # claves de bloques sugeridos en el editor

    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def build_prompt(self, context_blocks: list[dict]) -> str: ...

    def run(self, context_blocks: list[dict], log) -> AgentResult:
        prompt = self.build_prompt(context_blocks)
        log("info", f"prompt built ({len(prompt)} chars)")
        response = copilot_bridge.invoke(
            agent_type=self.type,
            system=self.system_prompt(),
            user=prompt,
            on_log=log,
        )
        return AgentResult(
            output=response.text,
            output_format=response.format,
            metadata=response.metadata,
        )
```

Cada subclase (`BusinessAgent`, `FunctionalAgent`, etc.) implementa los dos `@abstractmethod`. **No comparten estado**, no se conocen entre sí.

---

## `agent_runner.py` — el núcleo

```python
# agent_runner.py

def run_agent(
    agent_type: str,
    ticket_id: int,
    context_blocks: list[dict],
    user: str,
    chain_from: list[int] | None = None,
) -> int:
    """
    Crea una AgentExecution, la persiste en `running`, lanza la ejecución
    en thread, y devuelve el id. El cliente consulta /api/executions/:id
    o el SSE para seguir progreso.
    """
    agent = agents.registry.get(agent_type)
    if agent is None:
        raise UnknownAgentError(agent_type)

    exec_row = AgentExecution(
        ticket_id=ticket_id,
        agent_type=agent_type,
        input_context=context_blocks,
        chain_from=chain_from or [],
        status="running",
        started_by=user,
        started_at=now(),
    )
    db.session.add(exec_row)
    db.session.commit()

    log_streamer.open(exec_row.id)
    threading.Thread(
        target=_run_in_background,
        args=(agent, exec_row.id),
        daemon=True,
    ).start()

    return exec_row.id


def _run_in_background(agent: BaseAgent, exec_id: int):
    log = log_streamer.logger_for(exec_id)
    try:
        with new_session() as session:
            exec_row = session.get(AgentExecution, exec_id)
            result = agent.run(exec_row.input_context, log=log)
            exec_row.output = result.output
            exec_row.output_format = result.output_format
            exec_row.metadata_json = result.metadata
            exec_row.status = "completed"
            exec_row.completed_at = now()
            session.commit()
            log("info", f"✓ done ({result.metadata.get('duration_ms')}ms)")
    except CancelledError:
        _mark(exec_id, status="cancelled")
        log("warn", "× cancelled by user")
    except Exception as e:
        _mark(exec_id, status="error", error=str(e))
        log("error", f"× {e}")
    finally:
        log_streamer.close(exec_id)
```

**Decisiones explícitas:**

1. La ejecución es **fire-and-forget desde el HTTP handler**: el endpoint `/run` devuelve el `exec_id` en < 100ms. Toda la ejecución pesada vive en thread separado.
2. La cancelación se hace via `log_streamer.cancel(exec_id)` que setea un flag; el `copilot_bridge.invoke` chequea ese flag entre cada chunk de stream.
3. Los logs viven en memoria (buffer circular por exec) + dump a `data/logs/{exec_id}.log` al cerrar. El SSE feed lee del buffer en vivo y de archivo si la conexión llega tarde.
4. Errores se capturan y persisten — la fila siempre cierra con un status final.

---

## API HTTP — endpoints completos

| Método | Path | Body / Query | Devuelve | Notas |
|---|---|---|---|---|
| GET | `/api/health` | — | `{ok: true}` | smoke |
| GET | `/api/agents` | — | `[{type, name, description, inputs, outputs}]` | catálogo |
| POST | `/api/agents/run` | `{agent_type, ticket_id, context_blocks, chain_from?}` | `{execution_id, status: "running"}` | dispara ejecución |
| POST | `/api/agents/cancel/:exec_id` | — | `{ok: true}` | señala cancelación |
| GET | `/api/executions` | `?ticket_id=&agent_type=&status=&limit=` | `[Execution]` | con filtros |
| GET | `/api/executions/:id` | — | `Execution` | detalle completo |
| GET | `/api/executions/:id/logs` | — | `[LogLine]` | snapshot |
| GET | `/api/executions/:id/logs/stream` | — | SSE stream | live tail |
| POST | `/api/executions/:id/approve` | — | `Execution` | marca aprobada |
| POST | `/api/executions/:id/discard` | — | `Execution` | marca descartada |
| POST | `/api/executions/:id/publish-to-ado` | `{target: "comment" \| "task"}` | `{ado_url}` | escribe en ADO |
| GET | `/api/executions/:id/diff/:other_id` | — | `{left, right}` | para diff view |
| GET | `/api/tickets` | `?project=&search=` | `[Ticket]` | lectura desde ADO |
| GET | `/api/tickets/:id` | — | `Ticket` con últimas execs | |
| GET | `/api/packs` | — | `[PackDefinition]` | catálogo |
| POST | `/api/packs/start` | `{pack_id, ticket_id, options}` | `{pack_run_id, current_step}` | inicia pack |
| GET | `/api/packs/runs/:id` | — | `PackRunState` | |
| POST | `/api/packs/runs/:id/advance` | — | `PackRunState` | aprueba paso actual y avanza |
| POST | `/api/packs/runs/:id/pause` | — | `PackRunState` | |
| POST | `/api/packs/runs/:id/resume` | — | `PackRunState` | |
| DELETE | `/api/packs/runs/:id` | — | `{ok: true}` | abandonar |

Versionado: `Accept: application/vnd.stacky-agents.v1+json` (default v1; v2 cuando rompamos contrato).

CORS: configurado para `localhost:5173` en dev, dominio interno en prod.

---

## SSE — protocolo de logs

```
event: log
data: {"timestamp":"2026-04-23T09:10:08","level":"info","message":"sub-agent BATCH: skip","group":"explore"}

event: status
data: {"status":"running","step":"compose"}

event: output_chunk
data: {"chunk":"## 1. Traducción funcional → técnica\n\n"}

event: completed
data: {"execution_id":23,"duration_ms":14000}

event: error
data: {"message":"LLM timeout","retryable":true}
```

El cliente reconecta automáticamente con `Last-Event-ID` para reanudar desde el último evento recibido (no perdemos logs).

---

## Frontend — estructura de carpetas

```
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx                   ← bootstrap
    ├── App.tsx                    ← router (sólo /workbench por ahora)
    ├── theme.ts                   ← tokens CSS exportados
    ├── agents.ts                  ← catálogo cliente (5 agentes)
    ├── api/
    │   ├── client.ts              ← fetch wrapper + tipos
    │   ├── agents.ts              ← runAgent(), cancelAgent()
    │   ├── executions.ts
    │   ├── tickets.ts
    │   └── packs.ts
    ├── store/
    │   └── workbench.ts           ← Zustand store
    ├── hooks/
    │   ├── useAgentRun.ts         ← mutation + SSE
    │   ├── useTickets.ts
    │   ├── useExecutions.ts
    │   └── useAutoFillBlocks.ts
    ├── pages/
    │   └── Workbench.tsx
    └── components/
        ├── TopBar.tsx
        ├── PackBanner.tsx
        ├── TicketSelector.tsx
        ├── AgentSelector.tsx
        ├── AgentCard.tsx
        ├── PackList.tsx
        ├── PackLauncherModal.tsx
        ├── InputContextEditor.tsx
        ├── ContextBlock.tsx
        ├── TokenCounter.tsx
        ├── RunButton.tsx
        ├── OutputPanel.tsx
        ├── OutputHeader.tsx
        ├── OutputBody.tsx
        ├── OutputActions.tsx
        ├── DiffView.tsx
        ├── LogsPanel.tsx
        ├── LogLine.tsx
        ├── ExecutionHistory.tsx
        ├── ExecutionRow.tsx
        └── shared/
            ├── Card.tsx
            ├── Modal.tsx
            ├── Tooltip.tsx
            ├── EmptyState.tsx
            └── Skeleton.tsx
```

---

## Ciclo de vida de una ejecución (e2e)

```
[User]                                  [Frontend]                       [Backend]                            [Engine]
  │                                          │                                │                                  │
  │  click Run                               │                                │                                  │
  │─────────────────────────────────────────▶│                                │                                  │
  │                                          │  POST /api/agents/run          │                                  │
  │                                          │───────────────────────────────▶│                                  │
  │                                          │                                │  insert AgentExecution(running)  │
  │                                          │                                │  spawn thread                    │
  │                                          │  { execution_id, running }     │                                  │
  │                                          │◀───────────────────────────────│                                  │
  │                                          │                                │                                  │
  │                                          │  open SSE /executions/23/logs/stream                              │
  │                                          │───────────────────────────────▶│                                  │
  │                                          │                                │  thread: agent.run()             │
  │                                          │                                │─────────────────────────────────▶│
  │                                          │                                │                                  │  prompt
  │                                          │                                │                                  │  LLM stream...
  │                                          │  event: log {start}            │                                  │
  │                                          │◀───────────────────────────────│                                  │
  │                                          │  event: log {explore}          │                                  │
  │                                          │◀───────────────────────────────│                                  │
  │                                          │  event: output_chunk           │                                  │
  │                                          │◀───────────────────────────────│                                  │
  │                                          │                                │  thread: persist output          │
  │                                          │  event: completed              │                                  │
  │                                          │◀───────────────────────────────│                                  │
  │                                          │  invalidate executions query   │                                  │
  │                                          │  refetch                       │                                  │
  │                                          │───────────────────────────────▶│                                  │
  │                                          │  GET /api/executions/23        │                                  │
  │                                          │  { full data }                 │                                  │
  │                                          │◀───────────────────────────────│                                  │
  │  ve output                                │                                │                                  │
  │◀─────────────────────────────────────────│                                │                                  │
```

---

## Concurrencia y race conditions

### Múltiples ejecuciones del mismo ticket en paralelo
Permitido. Cada exec tiene su `id` único; persisten independientes. La UI advierte pero no bloquea.

### Misma ejecución consultada por dos clientes
SSE es 1-to-N: cualquier cliente con `EventSource` al stream recibe los mismos eventos. Útil para colaboración en vivo.

### Cancelación durante stream
`/api/agents/cancel/:exec_id` setea flag → el bucle de stream del LLM lo lee → emite `cancelled` por SSE → cierra. Tiempo de respuesta: < 1s.

### Doble-click en Run
El frontend deshabilita el botón mientras `state === 'running'`. El backend acepta el segundo POST igualmente: crea exec adicional. Es resiliente, no preventivo.

### Caída del backend mientras una exec corre
Al reiniciar, un job de reconciliación marca todas las execs en `running` como `failed (process killed)`. El operador las ve y decide retry.

---

## Seguridad y permisos

| Aspecto | Decisión |
|---|---|
| Auth | header `X-User-Email` por ahora; a futuro Azure AD via `msal-flask` |
| Autorización | una sola pinza: el usuario tiene que poder leer ADO. Si no, no ve tickets |
| ADO PAT | server-side, cargado de env (`ADO_PAT`); nunca expuesto al frontend |
| Secretos | `.env` ignorado por git; `config.py` carga con default a errores explícitos |
| SQL injection | SQLAlchemy con queries parametrizadas; no concatenar strings |
| XSS en outputs | `react-markdown` no permite raw HTML por default |
| CORS | whitelist explícita en `app.py` |
| Rate limit | server-side por user en `/api/agents/run` (10/min por defecto) |

---

## Observabilidad

- Logs estructurados JSON con `python-json-logger`. Cada log tiene `exec_id`, `user`, `agent_type` cuando aplica.
- Métricas:
  - count execs por agente / por status / por día
  - duración p50/p95/p99 por agente
  - tasa de aprobados vs descartados
  - tokens promedio por agente
- Endpoint `/api/admin/metrics` que devuelve esos números (futuro Prometheus).
- Tracing: opcional, OpenTelemetry-compatible, off por default.

---

## Deploy (referencial)

| Entorno | Backend | Frontend | BD |
|---|---|---|---|
| **dev local** | `python app.py` (5050) | `npm run dev` (5173) | SQLite file |
| **staging** | gunicorn detrás de nginx interno | nginx sirviendo `dist/` | Postgres compartido |
| **prod** | gunicorn + systemd | nginx + cache | Postgres con backups |

Variables de entorno principales:

```
ADO_ORG=UbimiaPacifico
ADO_PROJECT=Strategist_Pacifico
ADO_PAT=*****
DATABASE_URL=sqlite:///./data/stacky_agents.db
LLM_BACKEND=copilot           # copilot | claude | mock
LLM_MODEL=claude-sonnet-4-6
LOG_LEVEL=INFO
ALLOWED_ORIGINS=http://localhost:5173
```

---

## Lo que **no** hace este backend (intencional)

- No edita código del repo. El agente Developer prepara cambios y los devuelve como diffs / scripts; un job humano-disparado los aplica.
- No mueve tickets de estado en ADO automáticamente. Hay un endpoint `/publish-to-ado` que el operador llama explícitamente.
- No tiene cron interno. Si en el futuro se quiere automatizar, vivirá en otro servicio que llame a esta API.
- No mantiene "estado del ticket" propio. Lee ADO como source of truth.
