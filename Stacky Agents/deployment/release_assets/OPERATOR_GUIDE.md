# Stacky Agents - Guia de operador

## Abrir la app

Ejecutar `START.bat`. El navegador se abre en `http://localhost:5050`.

## Configurar proyectos

Desde la barra superior, crear o editar un proyecto y completar:

- carpeta del workspace local;
- tracker de issues;
- credenciales del tracker;
- rutas opcionales de documentacion tecnica y funcional.

Las credenciales se guardan localmente para el usuario de Windows.

## Diagnostico

Abrir `/diagnostics` desde la app para revisar backend, tracker, VS Code,
bridge local, base SQLite y logs. Usar "Exportar logs" cuando soporte pida
evidencia.

## Datos locales

No borrar estas carpetas salvo que soporte lo indique:

- `data/`: base local, logs y backups;
- `projects/`: configuracion por cliente/proyecto.

## Agentes GitHub Copilot

El deploy puede incluir `github_copilot_agents/` con los `.agent.md` del repo
de agentes de GitHub Copilot. Si la carpeta existe, Stacky la usa como fuente
de agentes por defecto. Para generar el deploy desde una ruta especifica:

```powershell
.\PrepararPublicacion.bat -GitHubCopilotAgentsRepo "C:\ruta\al\repo\de\agentes"
```

## Detener Stacky Agents

Cerrar la ventana de consola abierta por `START.bat`.
