# Stacky Agents - Release

Este paquete trae el backend congelado y el frontend compilado. No necesita
Python, Node.js, `requirements.txt` ni `node_modules` en la maquina destino.

## Pasos

1. Ejecutar `INSTALL.ps1` con PowerShell.
2. Ejecutar `START.bat`.

## Que incluye

- `backend/stacky-backend.exe` con las dependencias embebidas.
- `frontend/dist/` ya compilado.
- `vscode_extension/` con el ultimo `.vsix` disponible.
- `data/` y `projects/` como carpetas persistentes para configuracion local.

## Notas

- La app queda en `http://localhost:5050`.
- El backend sirve la UI desde el mismo proceso y el mismo puerto.
- Para cambiar el puerto, crear `data/runtime_config.json` con `{ "port": 5051 }`.
- Al actualizar, preservar `data/` y `projects/` para no perder configuracion.
