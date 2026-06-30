# Guía de instalación: codebase-memory-mcp para Codex CLI

> Plan 76 — Instalación opt-in. D1 confirmado para Codex CLI.

## Prerequisitos

- `gh` CLI instalado y autenticado
- Codex CLI instalado y configurado

## Pasos

### 1. Descargar y verificar el binario

```bash
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \
  --pattern "codebase-memory-mcp-windows-amd64.zip"

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

### 4. Configurar en `.codex/config.toml`

Crear o editar `.codex/config.toml` en el directorio del proyecto:

```toml
[mcp_servers.codebase-memory-mcp]
command = "C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe"
args = []
```

### 5. Activar el flag en Stacky

Desde el HarnessFlagsPanel (categoría "Avanzado / experimental"):
- Activar `STACKY_CODEBASE_MEMORY_MCP_ENABLED`

### 6. Verificar

Consultar `GET /api/codebase-memory-mcp/status` en el backend de Stacky.
