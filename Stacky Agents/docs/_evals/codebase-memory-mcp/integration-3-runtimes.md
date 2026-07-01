# F3 — Integración MCP en 3 runtimes + D4 (solapamiento)

> Plan 76 — Fase F3. Generado: 2026-06-30.

---

## E5 — Config MCP por runtime (D1)

### Runtime 1: Claude Code CLI — APROBADO

Declarar el server en `~/.claude/.mcp.json` o via `--mcp-config`:

```json
{
  "mcpServers": {
    "stacky": {
      "command": "<python-exe>",
      "args": ["<ruta-al-mcp-server-de-stacky>"],
      "env": {}
    },
    "codebase-memory-mcp": {
      "command": "C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe",
      "args": []
    }
  }
}
```

**Coexistencia con MCP interno de Stacky:**
- Stacky emite `{"mcpServers": {"stacky": {...}}}` (`services/stacky_mcp.py:64-65`)
- El server externo usa la clave `"codebase-memory-mcp"` — **distinta** de `"stacky"`
- Claude Code CLI soporta múltiples servers MCP simultáneos en `mcpServers`
- **Coexistencia confirmada por contrato de claves: sin colisión.**

**D1 Claude Code CLI = APROBADO**

---

### Runtime 2: Codex CLI — APROBADO

Configurar en `.codex/config.toml` (en el directorio del proyecto):

```toml
[mcp_servers.codebase-memory-mcp]
command = "C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe"
args = []
```

El README incluye explícitamente Codex CLI en la tabla de compatibilidad multi-agente con instrucciones de config file.

**D1 Codex CLI = APROBADO**

---

### Runtime 3: GitHub Copilot Pro (VS Code) — NO CONFIRMADO

- GitHub Copilot Pro no aparece en la tabla de compatibilidad de agentes del README de codebase-memory-mcp.
- VS Code soporta servidores MCP via la extensión GitHub Copilot (desde 2025), pero la integración específica con este binary externo no está documentada.
- Se requiere verificación manual: instalar el server y probar vía VS Code + Copilot Chat + herramientas MCP.

**D1 Copilot Pro = DUDOSO (no confirmado, no refutado)**

---

## D1 Global

**D1 = DUDOSO** (2/3 runtimes confirmados, 1 sin documentar)

- Claude Code CLI: APROBADO
- Codex CLI: APROBADO
- Copilot Pro: DUDOSO (requiere verificación manual)

---

## E4 — Solapamiento D4 (vs índices de Stacky)

### vs REPO_MAP.md
- `REPO_MAP.md` es un mapa estático Markdown generado por script externo. No es queryable en runtime.
- `codebase-memory-mcp` ofrece 14 tools MCP de query en tiempo real sobre el grafo.
- **No hay solapamiento: complementario.**

### vs MCP interno de Stacky (stacky_get_skill)
- Tool `stacky_get_skill` sirve las **skills de Stacky** (procedimientos de agente), no estructura de código del proyecto del operador.
- `codebase-memory-mcp` indexa el **código fuente** del proyecto (Python/C#/TS/SQL) y responde queries estructurales.
- **Dominios distintos: sin solapamiento.**

**D4 = APROBADO — complementario a ambos índices existentes.**

---

## Verificación de coexistencia de claves MCP

| Server | Clave en `mcpServers` | Propósito |
|--------|----------------------|-----------|
| Stacky interno | `"stacky"` (`stacky_mcp.py:65`) | Skills de Stacky |
| Externo Plan 76 | `"codebase-memory-mcp"` | Indexación de código del proyecto |

Claves distintas → sin colisión → ambos servers conviven en el config de Claude Code CLI.

---

## Plan 80: Estado de auto-inyección por runtime

> Plan 80 — wiring real. Generado: 2026-07-01. Este apéndice corrige la promesa
> del F3 original de este doc ("D1 Codex CLI = APROBADO" solo evaluaba soporte
> TOML documentado por el README externo, NO implica wiring automático de Stacky).

| Runtime         | Auto-inyección | Ruta soportada | Razón |
|---|---|---|---|
| Claude Code CLI | SÍ (F2)        | `--mcp-config` automático | `claude_code_cli_runner.py:595` ya escribe el config; `stacky_mcp.py::maybe_write_mcp_config` inyecta el 2º server (Plan 80 F2) |
| Codex CLI       | NO (3b)        | Guía manual `install-codex.md` | Sin rama MCP en `codex_cli_runner.py`; soporte TOML del binario documentado por el README externo, pero Stacky no lo cablea aún |
| Copilot Pro     | NO (F4)        | Guía manual `install-copilot-pro.md` | Bridge HTTP; no spawnea CLI |

### Nota crítica — Indexación previa (obligatoria antes de usar el MCP externo)

El server externo `{"command": binary_path, "args": []}` arranca **sin índice**. Las tools
`search_graph`, `get_code_snippet`, `trace_call_path` devuelven vacío si no se corrió
`index_repository` primero. El operador debe ejecutar **una sola vez** (y luego cuando el
codebase cambie significativamente):

```
codebase-memory-mcp index_repository --path "N:\GIT\RS\STACKY\Stacky"
```

O configurar indexación automática: `codebase-memory-mcp config set auto_index true`
(re-indexa cambios en background vía git polling). **Sin este paso, activar el flag produce
un MCP funcional pero con tools que devuelven vacío — el agente degrada silenciosamente.**

### Plan 80b (futuro): Opción 3a para Codex

Prerequisito: verificar que Codex CLI acepta `[mcp_servers.X] command="..." args=[]` en un
`config.toml` pasado por-run (o flag `--config`).
Si se verifica: crear `build_codex_mcp_toml_block(binary_path) -> str | None` en
`codebase_memory_mcp_wiring.py` y cablear en `codex_cli_runner.py` análogo a F2 de este
plan, con su propio catch que no rompa el run.
