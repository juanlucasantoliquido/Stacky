# Stacky VS Code Extension

Integra el pipeline Stacky directamente en VS Code y expone el bridge HTTP que
consume `auto_enter_daemon.py` y `copilot_bridge.py`.

## Endpoints del bridge (127.0.0.1:5051)

| Método | Path        | Descripción                                                    |
|--------|-------------|----------------------------------------------------------------|
| GET    | `/health`   | Liveness probe. Retorna `{ok, version, copilotChatVersion, uptimeSeconds}`. |
| POST   | `/submit`   | Dispara `Ctrl+Enter` en Copilot Chat (wrapper sobre `/keypress ctrl+enter`). |
| POST   | `/keypress` | Ejecuta keybindings o comandos por nombre. Body: `{key|command}`. |
| POST   | `/invoke`   | Stub Fase 1 — responde `ok=false` para que el caller use su fallback UI. |
| POST   | `/approve`  | **501 Not Implemented** — reservado para Fase 2.               |

## Build

```powershell
cd Tools\Stacky\vscode_extension
npm install
npm run compile
```

Para empaquetar e instalar el VSIX:

```powershell
npx vsce package --no-dependencies
code --install-extension stacky-vscode-1.1.0.vsix --force
```

Tras instalar, recargar la ventana de VS Code (F1 → `Developer: Reload Window`)
para que la nueva versión empiece a servir los endpoints nuevos.

## Verificación manual

```powershell
curl http://127.0.0.1:5051/health
curl -X POST http://127.0.0.1:5051/submit
```
