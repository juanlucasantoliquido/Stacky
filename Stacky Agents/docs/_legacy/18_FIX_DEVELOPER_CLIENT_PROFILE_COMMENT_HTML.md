# Fix — Flujo del agente Developer: client-profile + `comment.html` (ADO)

> Incidencia (ADO 12): al invocar al agente **Developer** desde Stacky, el
> `client-profile` no llegaba al prompt y el Developer no generaba `comment.html`,
> así que Stacky no podía publicar el comentario en Azure DevOps. El agente
> **Técnico** sí funcionaba. Este documento describe la causa raíz, el arreglo y
> cómo validarlo.

## Causa raíz (dos problemas independientes)

El operador lanza al Developer con runtime **GitHub Copilot** → frontend llama
`POST /api/agents/open-chat` → la extensión abre **Copilot Chat** en VS Code; el
agente toma su persona del `.agent.md` canónico (`config.VSCODE_PROMPTS_DIR =
<STACKY_HOME>/agents`), implementa, **escribe `Agentes/outputs/{ADO_ID}/comment.html`**
y el `output_watcher` (Modo B) lo detecta y publica en ADO.

1. **RC1 — El `Developer.agent.md` (v2.0.0) nunca instruía escribir `comment.html`.**
   Su `PASO 5` sólo hacía un `PATCH status=completed` sin generar el artefacto.
   El `TechnicalAnalyst.agent.md` (y `DevPacifico.agent.md`) sí escriben
   `comment.html` + `comment.meta.json` + `PATCH` con `html_output_path` y
   `target_ado_state`. Sin el archivo, el `output_watcher` Modo B no tenía nada
   que publicar → "el Developer no genera los archivos".

2. **RC2 — `open_chat` no inyectaba el bloque `client-profile`.**
   `api/agents.py::open_chat` armaba el mensaje sin pasar por
   `context_enrichment.enrich_blocks`, así que el bloque `client-profile` (que sí
   se inyecta en los runtimes `/run`, `codex_cli` y `claude_code_cli`) **nunca
   llegaba** al prompt interactivo. El **Técnico** no lo notaba porque su
   `.agent.md` tiene los datos de Pacífico hardcodeados; el **Developer** es
   *cliente-agnóstico* y depende del `client-profile` para conocer rutas/build/
   estados → arrancaba "a ciegas".

> Detalle de despliegue que ocultó el bug: una corrección previa quedó sólo en
> `backend/agents/Developer.agent.md` (única copia trackeada en git), pero la
> **fuente autorizada de release es `backend/Stacky/agents`** (gitignored) y la
> copia viva del deploy (`DeployStackyAgents/Stacky/agents`) seguía en v2.0.0.

## Qué se cambió

### 1. `client-profile` también en el flujo interactivo (RC2)
- **`backend/services/context_enrichment.py`** — se extrajo
  `build_client_profile_block(project_name, log)` como *seam* único de armado del
  bloque. `_inject_client_profile_block` ahora delega en él (se conserva la
  deduplicación). Comportamiento de `enrich_blocks` (runtimes batch/CLI) idéntico.
- **`backend/api/agents.py::open_chat`** — tras `ensure_project_vscode`, llama a
  `build_client_profile_block(project_ctx.stacky_project_name)` y agrega el bloque
  al `message` (`## Perfil del cliente: …` + JSON). Best-effort: respeta el flag
  `STACKY_INJECT_CLIENT_PROFILE` y degrada sin romper si no hay perfil/proyecto.
  Ahora **ambos caminos** (open-chat y /run + CLI) entregan el mismo perfil.

### 2. `Developer.agent.md` genera `comment.html` (RC1)
- `Developer.agent.md` actualizado a **v2.1.1**, alineado con el Técnico:
  - `PASO 5` escribe `Agentes/outputs/{ADO_ID}/comment.html` y
    `Agentes/outputs/{ADO_ID}/comment.meta.json`, y hace `PATCH
    /api/tickets/by-ado/{ADO_ID}/stacky-status` con `html_output_path` y
    `target_ado_state`.
  - Sección `OUTPUT — Formato HTML` para el comentario de implementación.
  - `target_ado_state` se lee de
    `client_profile.tracker_state_machine.developer.next_state_ok`
    (ej. `Reviewed by Dev`) / `…blocked_state`, en vez de hardcodear `Done`.
  - `stacky_requires_client_profile: true`.
- Propagado a las 4 ubicaciones (idénticas, sha `7e1aadb3580f`):
  `backend/agents/` (git), `backend/Stacky/agents/` (fuente de release),
  `DeployStackyAgents/github_copilot_agents/` (bundle) y
  `DeployStackyAgents/Stacky/agents/` (**canónico vivo que lee el deploy**).
  Checksums de `manifest.json` actualizados en ambos `Stacky/agents`.

> El `output_watcher` no revierte estos archivos (`materialize_agents` no
> sobrescribe los existentes) y la copia viva ya quedó corregida, así que el
> fix surte efecto sin reconstruir el deploy.

## Cómo validar

1. **Tests backend** (desde `Stacky Agents/backend`):
   ```
   python -m pytest tests/test_open_chat_ado_enrichment.py \
     tests/test_context_enrichment_client_profile.py \
     tests/test_client_profile.py tests/test_ado_delegation_contract.py -q
   ```
   Incluye dos tests nuevos en `test_open_chat_ado_enrichment.py`:
   `test_open_chat_message_includes_client_profile` y
   `test_open_chat_skips_client_profile_when_flag_off`.

2. **End-to-end (ADO 12):** lanzar el Developer (runtime GitHub Copilot) sobre
   ADO 12. Verificar en el prompt que aparece `## Perfil del cliente: …` y que el
   agente escribe `Agentes/outputs/12/comment.html` (+ `comment.meta.json`). El
   `output_watcher` Modo B publica el comentario en ADO en ~3s aunque el `PATCH`
   final falle.

3. **No-regresión del Técnico:** el bloque `client-profile` se agrega para todos
   los agentes en open-chat, pero es aditivo; `TechnicalAnalyst.agent.md` lo
   ignora (usa sus datos hardcodeados) y sigue funcionando igual.

## Alcance (scope) — otras personas "dev"

El frontend mapea **cualquier** `.agent.md` cuyo nombre contenga `dev` a
`agent_type=developer` (`frontend/src/services/agentLaunch.ts:13`). En el dir
canónico conviven varias: `Developer` (cliente-agnóstico, **arreglado**),
`DevPacifico` (hardcodeado Pacífico, ya escribía `comment.html`), y otras que
**no** instruyen `comment.html` (`dev`, `DevAutomation`, `DevPacifico2`,
`DevStack1/2/3`, `DevStackMobile1`, `DevStandAlone`).

- **RC2 (client-profile en open-chat)** es *filename-agnóstico*: beneficia a
  todas por igual.
- **RC1 (instrucción de `comment.html`)** es *por archivo*: solo se corrigió
  `Developer.agent.md` (el que la incidencia nombra). Si el run que fallaba para
  ADO 12 usó **otra** persona dev de las de cero `comment.html`, el síntoma
  persistiría con esa. Recomendado: confirmar qué `.agent.md` se eligió en el run
  fallido; si era otra, replicarle el `PASO 5` (o derivarla de `Developer.agent.md`).
