"""Plan 76 — Helpers PUROS para el estado de integración de codebase-memory-mcp.

Estas funciones son PURAS:
- No ejecutan el binario externo.
- No hacen red (no abren sockets).
- Solo leen config y retornan strings/dicts.

Refs:
- `config.Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED`
- `services/harness_flags.py:FLAG_REGISTRY` (flag editable por UI, categoría "avanzado")
- `docs/_evals/codebase-memory-mcp/` (guías de instalación)
"""
from __future__ import annotations

_VALID_RUNTIMES = ("claude_code", "codex", "copilot_pro")

_GUIDES: dict[str, str] = {
    "claude_code": """\
# Instalación de codebase-memory-mcp para Claude Code CLI

## 1. Descargar el binario (Windows)

```bash
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \\
  --pattern "codebase-memory-mcp-windows-amd64.zip"
```

Extraer en `C:\\tools\\codebase-memory-mcp\\`.

## 2. Verificar la firma (SLSA / cosign)

```bash
gh attestation verify codebase-memory-mcp-windows-amd64.zip \\
  --repo DeusData/codebase-memory-mcp
```

## 3. Indexar el repo

```bash
C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe index_repository \\
  --path "N:\\GIT\\RS\\STACKY\\Stacky"
```

## 4. Configurar en `~/.claude/.mcp.json`

```json
{
  "mcpServers": {
    "stacky": {
      "<comentario>": "El MCP interno de Stacky (clave 'stacky') coexiste con el externo"
    },
    "codebase-memory-mcp": {
      "command": "C:\\\\tools\\\\codebase-memory-mcp\\\\codebase-memory-mcp.exe",
      "args": []
    }
  }
}
```

> **Importante:** la clave del server externo es `"codebase-memory-mcp"` — distinta de la
> clave interna `"stacky"` de Stacky. Ambos servers coexisten sin colisión.

## 5. Activar el flag

Desde el HarnessFlagsPanel (categoría "Avanzado / experimental"), activar
`STACKY_CODEBASE_MEMORY_MCP_ENABLED`.

## 6. Verificar

Consultar `GET /api/codebase-memory-mcp/status` — debe devolver `{"enabled": true, ...}`.
""",

    "codex": """\
# Instalación de codebase-memory-mcp para Codex CLI

## 1. Descargar e instalar el binario

```bash
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \\
  --pattern "codebase-memory-mcp-windows-amd64.zip"
```

Extraer en `C:\\tools\\codebase-memory-mcp\\`.

## 2. Indexar el repo

```bash
C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe index_repository \\
  --path "N:\\GIT\\RS\\STACKY\\Stacky"
```

## 3. Configurar en `.codex/config.toml` (directorio del proyecto)

```toml
[mcp_servers.codebase-memory-mcp]
command = "C:\\\\tools\\\\codebase-memory-mcp\\\\codebase-memory-mcp.exe"
args = []
```

## 4. Activar el flag

Desde el HarnessFlagsPanel (categoría "Avanzado / experimental"), activar
`STACKY_CODEBASE_MEMORY_MCP_ENABLED`.
""",

    "copilot_pro": """\
# Instalación de codebase-memory-mcp para GitHub Copilot Pro (VS Code)

> **Nota (D1 DUDOSO):** GitHub Copilot Pro no está explícitamente listado en la tabla
> de compatibilidad de runtimes MCP del README de codebase-memory-mcp. La instalación
> puede funcionar si VS Code + Copilot soportan MCP servers externos, pero se requiere
> verificación manual.

## 1. Descargar e instalar el binario

```bash
gh release download v0.8.1 --repo DeusData/codebase-memory-mcp \\
  --pattern "codebase-memory-mcp-windows-amd64.zip"
```

Extraer en `C:\\tools\\codebase-memory-mcp\\`.

## 2. Indexar el repo

```bash
C:\\tools\\codebase-memory-mcp\\codebase-memory-mcp.exe index_repository \\
  --path "N:\\GIT\\RS\\STACKY\\Stacky"
```

## 3. Configurar en VS Code (`settings.json` o `.vscode/mcp.json`)

```json
{
  "mcp": {
    "servers": {
      "codebase-memory-mcp": {
        "command": "C:\\\\tools\\\\codebase-memory-mcp\\\\codebase-memory-mcp.exe",
        "args": []
      }
    }
  }
}
```

> Verificar que la extensión GitHub Copilot de VS Code soporte MCP servers externos.
> Si no funciona, usar la integración por Claude Code CLI que sí está confirmada.

## 4. Activar el flag

Desde el HarnessFlagsPanel (categoría "Avanzado / experimental"), activar
`STACKY_CODEBASE_MEMORY_MCP_ENABLED`.
""",
}


def mcp_installation_status() -> dict:
    """Lee el flag de config y devuelve el estado de la integración.

    PURA: no ejecuta el binario, no hace red, solo lee config.

    Returns:
        dict con al menos:
            enabled (bool): True si STACKY_CODEBASE_MEMORY_MCP_ENABLED está ON.
            installed_hint (str): mensaje de guía al operador.
    """
    from config import Config
    enabled = Config.STACKY_CODEBASE_MEMORY_MCP_ENABLED
    if enabled:
        installed_hint = (
            "Flag activado. Asegurate de haber instalado el binario externo "
            "codebase-memory-mcp y de haberlo configurado en el runtime del agente. "
            "Ver guías en 'guides' de esta respuesta."
        )
    else:
        installed_hint = (
            "Flag desactivado (default). El servidor externo codebase-memory-mcp "
            "no está integrado. Activá el flag desde la UI (HarnessFlagsPanel, "
            "categoría 'Avanzado / experimental') para habilitar la integración."
        )
    return {
        "enabled": enabled,
        "installed_hint": installed_hint,
        "flag": "STACKY_CODEBASE_MEMORY_MCP_ENABLED",
        "external_repo": "https://github.com/DeusData/codebase-memory-mcp",
    }


def build_installation_guide(runtime: str) -> str:
    """Genera el markdown de instalación para el runtime dado.

    PURA: no ejecuta el binario, no hace red, solo retorna strings.

    Args:
        runtime: uno de "claude_code", "codex", "copilot_pro".

    Returns:
        str: markdown con instrucciones de instalación para ese runtime.

    Raises:
        ValueError: si runtime no es uno de los valores válidos.
    """
    if runtime not in _VALID_RUNTIMES:
        raise ValueError(
            f"runtime inválido: '{runtime}'. "
            f"Valores válidos: {', '.join(_VALID_RUNTIMES)}"
        )
    return _GUIDES[runtime]
