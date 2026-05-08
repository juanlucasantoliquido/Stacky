# Stacky Agents — VS Code Extension (FA-24)

Corré agentes de Stacky directamente desde VS Code, sin abrir browser.

## Build

```bash
cd "Tools/Stacky Agents/vscode_extension"
npm install
npm run compile
```

## Probar (development mode)

1. Abrí esta carpeta en VS Code.
2. F5 → abre Extension Development Host.
3. En la nueva ventana, comandos disponibles via Cmd/Ctrl+Shift+P:
   - **Stacky: Run agent on current ticket**
   - **Stacky: Include this file as context**
   - **Stacky: Include selection as context**
   - **Stacky: Open Workbench**
   - **Stacky: Set active ticket**

## Configuración

`stackyAgents.apiBase` — URL del backend (default `http://localhost:5050`)
`stackyAgents.userEmail` — email para `X-User-Email` header

## Status bar

El indicador inferior izquierdo muestra el ticket activo. Click → cambiar.

## Empaquetado

```bash
npx @vscode/vsce package
```

Esto genera `stacky-agents-0.1.0.vsix` que se puede instalar con:

```bash
code --install-extension stacky-agents-0.1.0.vsix
```
