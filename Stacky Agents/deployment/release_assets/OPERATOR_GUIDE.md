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

## Agentes Stacky

Los `.agent.md` incluidos en el deploy viven en `Stacky/agents`. Esa carpeta es
la fuente unica que Stacky usa para listar y lanzar agentes.

## Detener Stacky Agents

Cerrar la ventana de consola abierta por `START.bat`.
