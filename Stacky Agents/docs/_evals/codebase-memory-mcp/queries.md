# F2 — Queries congeladas para PoC de tokens

> Plan 76 — Fase F2. Generado: 2026-06-30.  
> Sub-árbol DEFAULT: `Stacky Agents/backend` (Python) + `Stacky Agents/frontend/src` (TypeScript).  
> Commit SHA base: HEAD de rama `codex/subida-cambios-pendientes` al 2026-06-30.

---

## Protocolo de medición

**Sub-árbol:** El propio repo de Stacky (default — cero trabajo del operador).
- `Stacky Agents/backend/` — Python
- `Stacky Agents/frontend/src/` — TypeScript

**Runtime de medición:** Claude Code CLI (el más documentado).  
**Modelo:** el mismo en ambos modos (baseline vs MCP) para comparabilidad.

**Dos modos por query:**
1. **Baseline:** el agente resuelve con grep/Read de archivos (sin MCP codebase-memory-mcp)
2. **Con MCP:** el agente resuelve vía tool `search_graph` o `trace_path` de codebase-memory-mcp

**Métrica:** tokens de la transcripción real (input_tokens + output_tokens según la API de Claude).

---

## 10 queries estructurales canónicas (versionadas)

| # | Query | Tool MCP esperada |
|---|-------|-------------------|
| Q1 | "¿Dónde se define la función `build_agent_env`?" | `search_graph` / `search_code` |
| Q2 | "¿Quién llama a `mcp_installation_status`?" | `trace_path` |
| Q3 | "¿Qué archivos pertenecen al módulo `harness/`?" | `get_architecture` |
| Q4 | "¿Qué tipos usa la función `_maybe_autopublish_epic`?" | `query_graph` |
| Q5 | "Lista todas las funciones del archivo `tickets.py`" | `search_code` + `get_code_snippet` |
| Q6 | "¿Qué funciones importan `FLAG_REGISTRY`?" | `search_graph` |
| Q7 | "¿Cuál es la estructura de la clase `TrackerProvider`?" | `get_architecture` |
| Q8 | "¿Qué archivos TS importan `HarnessFlagsPanel`?" | `trace_path` |
| Q9 | "¿Qué funciones modifican la tabla `Execution` en la DB?" | `query_graph` |
| Q10 | "¿Qué endpoints registra el blueprint `api_bp`?" | `search_code` |

---

## Cómo correr la PoC

```bash
# 1. Descargar e instalar codebase-memory-mcp (Windows):
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \
  --pattern "codebase-memory-mcp-windows-amd64.zip"
unzip codebase-memory-mcp-windows-amd64.zip -d C:\tools\codebase-memory-mcp

# 2. Indexar el sub-árbol DEFAULT (registrar el commit SHA):
git -C "N:\GIT\RS\STACKY\Stacky" rev-parse HEAD > commit_sha.txt
C:\tools\codebase-memory-mcp\codebase-memory-mcp.exe index_repository \
  --path "N:\GIT\RS\STACKY\Stacky\Stacky Agents"

# 3. Modo baseline (sin MCP): correr claude con cada query sin --mcp-config
# 4. Modo MCP: correr claude con --mcp-config apuntando al server
# 5. Comparar tokens de la transcripción API (usar tiktoken o la telemetría de Stacky)

# Gate egress (deny-egress):
# En Windows: deshabilitar el adaptador de red antes de indexar/queries
# O usar Windows Firewall con regla de bloqueo de salida para el proceso
```

---

## Criterios de aceptación de la PoC

- `delta_tokens = tokens_grep_promedio - tokens_mcp_promedio > 0` → D5 APROBADO/DUDOSO
- `sin_ejecucion_de_codigo == true` → verificar que indexar no ejecuta código del repo
- `egress_local_only == true` → indexación + queries sin tráfico de red saliente → D9 APROBADO
