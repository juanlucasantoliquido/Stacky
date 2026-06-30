# Guía de instalación: codebase-memory-mcp para GitHub Copilot Pro (VS Code)

> Plan 76 — D1 DUDOSO para Copilot Pro: no está en la tabla de compatibilidad del README.
> Verificar que la extensión de GitHub Copilot en VS Code soporte MCP servers externos
> antes de usar en producción. Si no funciona, usar Claude Code CLI (D1 confirmado).

## Prerequisitos

- VS Code con extensión GitHub Copilot Pro instalada y activa
- `gh` CLI instalado y autenticado

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

### 4. Configurar en VS Code

Agregar en `settings.json` (o `.vscode/mcp.json` si tu versión de Copilot lo soporta):

```json
{
  "mcp": {
    "servers": {
      "codebase-memory-mcp": {
        "command": "C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe",
        "args": []
      }
    }
  }
}
```

### 5. Activar el flag en Stacky

Desde el HarnessFlagsPanel (categoría "Avanzado / experimental"):
- Activar `STACKY_CODEBASE_MEMORY_MCP_ENABLED`

### 6. Verificar compatibilidad

Si Copilot Pro en VS Code no expone los tools MCP de codebase-memory-mcp,
cambiar al runtime Claude Code CLI que sí los soporta (D1 confirmado).
