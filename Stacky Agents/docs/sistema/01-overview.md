# 01 — Overview

← [INDEX](INDEX.md) · hermanos: [02-arquitectura](02-arquitectura.md) · [05-agentes-runtimes](05-agentes-runtimes.md)

## Qué es
Stacky Agents es una aplicación de escritorio/web (backend Flask + SPA React) que orquesta **agentes de IA**
sobre los tickets de un issue tracker (Azure DevOps por defecto; también Jira y Mantis) para asistir el ciclo
de desarrollo: del brief de negocio a la épica, del análisis funcional/técnico al desarrollo, QA y cierre.
[V: app.py:71-139 maneja jira/mantis/azure_devops; agents/__init__.py:10-22 registry]

## Propósito
- Convertir texto libre del cliente en Épicas estructuradas (Business Agent) y publicarlas en ADO. [V: api/agents.py:564-669 run_brief; manifest.json:13]
- Ejecutar agentes (functional/technical/developer/qa/debug/pr-review) contra un ticket, vía distintos runtimes. [V: agents/__init__.py:10-22]
- Cerrar el loop automáticamente: detectar artifacts producidos por el agente, crear Tasks/comentarios en el tracker, y recuperar runs colgados. [V: app.py:308-333 watchers; services/output_watcher.py docstring]
- Amplificar al operador humano, no reemplazarlo (human-in-the-loop). [INF: MEMORY human-in-the-loop-fundamental; EXCEPCIÓN: brief→épica auto-publica]

## Actores / consumidores
| Actor | Rol | Conf. |
|-------|-----|-------|
| Operador humano (mono-usuario) | Lanza runs, revisa, aprueba/descarta, configura | [V: app.py:422 X-User-Email como identidad sin validar] |
| Agentes IA (Business/Functional/Technical/Developer/QA/Debug/PRReview/Custom) | Ejecutan el trabajo | [V: agents/__init__.py:10-22] |
| Runtimes externos (GitHub Copilot, Codex CLI, Claude Code CLI, VS Code bridge) | Motor de inferencia | [V: agent_runner.py:141,218,293; config.py:75 LLM_BACKEND] |
| Issue trackers (Azure DevOps / Jira / Mantis) | Fuente de tickets y destino de Tasks/comentarios | [V: app.py:71-139] |
| Otros sistemas (CI/Slack/dashboards) | Reciben webhooks `exec.completed` | [V: services/webhooks.py docstring] |

## Casos de uso principales
1. **Brief → Épica**: el operador pega un brief, el Business Agent genera HTML de épica y se publica en ADO (auto-publica sin aprobación, por pedido explícito). [V: api/agents.py:564-669; config.py:702-704 STACKY_EPIC_AUTOPUBLISH_BACKEND]
2. **Run de agente sobre un ticket**: `POST /api/agents/run` despacha el agente al runtime elegido. [V: api/agents.py:339]
3. **Cierre automático de tareas**: output_watcher / manifest_watcher detectan artifacts y cierran runs huérfanos. [V: app.py:308-333]
4. **Sincronización de tickets** desde el tracker al arrancar y on-demand. [V: app.py:55-139 _startup_sync; api/tickets.py:503 /sync]
5. **Revisión / historial / diagnóstico** vía tabs del SPA. [V: frontend/src/App.tsx:205-215]

## Fuera de alcance (de esta doc)
- Detalle del frontend componente-por-componente (75 componentes). Se documenta la estructura, no cada uno. [V: CLAUDE.md frontend/src/components 75]
- Detalle de los 137 servicios uno por uno; se cubren los que `app.py` arranca/importa. [V: 137 archivos en services/]
- El instalador/deploy PowerShell y `vscode_extension/` (fuera del núcleo runtime). [INF: alcance de la consigna]

## Supuestos
- Windows es el SO objetivo (mimetypes/truststore, paths). [V: app.py:8-28 comentarios Windows]
- Hay un proyecto activo configurado en `projects/<name>/config.json` para resolver tracker, workspace_root y agents. [V: runtime_paths.py:66-96; project_manager]
- En deploy congelado, los paths se resuelven desde el ejecutable (`is_frozen()`). [V: runtime_paths.py:26-63]
