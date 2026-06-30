# Guía de instalación: codebase-memory-mcp para Claude Code CLI

> Plan 76 — Instalación opt-in. El operador debe completar la PoC de `poc-metrics.md`
> (especialmente D9/egress) antes de usar en repos de clientes.

## Prerequisitos

- `gh` CLI instalado y autenticado
- Acceso a GitHub (para descargar releases y verificar attestation)
- Claude Code CLI configurado con `~/.claude/.mcp.json`

## Pasos

### 1. Descargar y verificar el binario

```bash
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \
  --pattern "codebase-memory-mcp-windows-amd64.zip" \
  --pattern "codebase-memory-mcp-windows-amd64.zip.bundle"

# Verificar firma (SLSA / cosign):
gh attestation verify codebase-memory-mcp-windows-amd64.zip \
  --repo DeusData/codebase-memory-mcp
```

### 2. Extraer

```bash
unzip codebase-memory-mcp-windows-amd64.zip -d C:\tools\codebase-memory-mcp
```

### 3. Indexar el codebase

```bash
C:\tools\codebase-memory-mcp\codebase-memory-mcp.exe index_repository \
  --path "N:\GIT\RS\STACKY\Stacky"
```

### 4. Configurar el server MCP

Editar `~/.claude/.mcp.json` (o el `--mcp-config` de Stacky):

```json
{
  "mcpServers": {
    "stacky": {
      "command": "<python-exe>",
      "args": ["<ruta-al-stacky-mcp-server>"]
    },
    "codebase-memory-mcp": {
      "command": "C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe",
      "args": []
    }
  }
}
```

> La clave `"codebase-memory-mcp"` es distinta de la interna `"stacky"` — coexisten sin colisión.

### 5. Activar el flag en Stacky

Desde el HarnessFlagsPanel (categoría "Avanzado / experimental"):
- Activar `STACKY_CODEBASE_MEMORY_MCP_ENABLED`

### 6. Verificar

```bash
curl http://localhost:5050/api/codebase-memory-mcp/status
# Debe retornar: {"enabled": true, ...}
```
