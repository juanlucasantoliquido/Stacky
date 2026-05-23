# Stacky Agents - Instalacion

Este paquete contiene Stacky Agents listo para ejecutar en Windows: backend
congelado, frontend compilado y la extension de VS Code incluida.

## Instalacion

1. Ejecutar `INSTALL.ps1` con PowerShell.
2. Esperar el smoke test final.
3. Ejecutar `START.bat`.

La app queda disponible en `http://localhost:5050`.

## Actualizacion

Instalar una version nueva sobre la anterior preserva `data/` y `projects/`.
Esas carpetas contienen la base local, backups, logs y configuracion de
proyectos del operador.

## Puerto

Para cambiar el puerto, crear o editar `data/runtime_config.json`:

```json
{ "port": 5051 }
```
