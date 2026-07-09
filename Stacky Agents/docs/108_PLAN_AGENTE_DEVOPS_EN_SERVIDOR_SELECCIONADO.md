# Plan 108 — El agente DevOps opera EN el servidor seleccionado (anclaje remoto real)

**Estado:** PROPUESTO
**Versión:** v1
**Fecha:** 2026-07-08
**Issue del operador:** "El agente de DevOps NO está entrando al servidor remoto seleccionado:
busca directorios, ejecuta comandos y explora archivos en MI computadora local en vez de
hacerlo en el servidor que seleccioné en el panel."

---

## 1. Objetivo y KPI

Cuando el operador tiene un servidor seleccionado en el panel DevOps, TODA operación del
agente DevOps sobre ese servidor (exploración de directorios, comandos, lectura de archivos,
plan/apply de ambientes) debe ejecutarse **en el servidor remoto** vía el riel WinRM auditado
del Plan 105 (`services/remote_exec.py`), nunca en la máquina local del operador. Sin servidor
seleccionado (o con las flags OFF) el comportamiento es **byte-idéntico** al actual.

**KPI/impacto:**
- Con servidor seleccionado: 100% de los comandos del agente sobre el servidor quedan en la
  auditoría JSONL del alias (`read_audit(alias)` devuelve >0 entradas `kind:"exec"` tras un turno).
- 0 exploraciones del filesystem local para pedidos "sobre el servidor" (verificable: el prompt
  del turno contiene el contrato de consola remota y la prohibición explícita de tools locales).
- Bugs P0 de la consola remota (Plan 105) reparados: crear conversación de consola deja de dar
  500 (hoy es un `TypeError` garantizado, ver §2 RC2).

---

## 2. Diagnóstico de causa raíz (evidencia archivo:línea, verificada 2026-07-08)

El síntoma tiene TRES causas raíz independientes. Las tres se corrigen en este plan.

### RC1 — El chat del agente DevOps (Plan 90) no tiene NINGUNA noción de servidor

- `Stacky Agents/frontend/src/components/devops/DevOpsAgentSection.tsx:65` — el frontend llama
  `DevOpsAgentApi.start({ project, message, runtime })`: **no envía ningún `server_alias`**,
  aunque `ctx.selectedServer` está disponible (lo publica `DevOpsPage.tsx:159-173` y lo
  persiste en `localStorage 'stacky.devops.selectedServer'`).
- `Stacky Agents/backend/api/devops_agent.py:29-99` — `start_conversation()` no acepta servidor.
- `Stacky Agents/backend/api/devops_agent.py:219-252` — `_launch_turn()` arma un
  `context_blocks` con el mensaje crudo (`id="devops-chat"`, líneas 231-237) y llama
  `agent_runner.run_agent(...)`, que lanza el runtime CLI (`claude_code_cli` / `codex_cli`)
  **en la máquina local del operador**, sobre el workspace del proyecto, con sus herramientas
  nativas de shell/filesystem locales. El prompt **no contiene ningún contrato de ejecución
  remota**, por lo que el agente responde "¿qué hay en D:\Apps?" listando el disco local.

**Conclusión RC1:** no es que el agente "elija mal": no existe el cable. La selección de
servidor del panel jamás llega al turno del agente.

### RC2 — El único camino remoto existente (consola del Plan 105) está ROTO en producción

`api/devops_remote_console.py` (Plan 105 F2) llama a `_launch_turn` del Plan 90 con una firma
que NO existe, por lo que crear una conversación de consola lanza `TypeError` ⇒ HTTP 500:

- `api/devops_remote_console.py:212-219` y `:275-282` — llama
  `_launch_turn(ticket_id=..., message=..., runtime=..., model=..., effort=..., user=...)`.
  La firma real es `api/devops_agent.py:219-227`:
  `_launch_turn(*, conversation_id, project, message, runtime, model_override, effort_override)`.
  `ticket_id`, `model`, `effort` y `user` son kwargs inexistentes ⇒ `TypeError`.
- `api/devops_remote_console.py:224` y `:284` — hace `turn_result.get("execution_id")`, pero
  `_launch_turn` retorna una **tupla** `(execution_id, error_response)`
  (`api/devops_agent.py:276`), no un dict.
- `api/devops_remote_console.py:253` — `from api.devops_agent import _send_input, _launch_turn`:
  **`_send_input` no existe** en `devops_agent.py` (el real es
  `services/claude_code_cli_runner.py:297 send_input(...)`) ⇒ `ImportError` en el camino "vivo".
- `api/devops_remote_console.py:255-256` — usa `ticket.executions[-1].state`; el atributo del
  modelo es `status` (patrón correcto: `api/devops_agent.py:120-128`, que consulta
  `AgentExecution.status`). Además lee `ticket` fuera del `session_scope` (detached instance,
  `devops_remote_console.py:246-249`).
- **Por qué el falso verde:** `tests/test_plan105_remote_console_api.py:222` mockea
  `api.devops_agent._launch_turn` con `return_value={"execution_id": "exec1"}` — un mock con
  kwargs y contrato de retorno que el símbolo real no tiene. El mock ocultó los 4 defectos.

### RC3 — Plan/apply de ambientes (Planes 89/107) evalúan el filesystem LOCAL

- `services/environment_init.py:153-179` — `plan_environment()` decide `root_exists`,
  `to_create/exists_ok/conflict` con `os.path.isdir/os.path.exists` **del host del backend**
  (la máquina del operador); `apply_environment()` crea con `os.makedirs` local (docstring
  línea 4). Si `environment_root` es una ruta pensada para el servidor (p.ej. `D:\Apps\Prod`),
  el preview del árbol (Plan 107, `sandbox_active`, `DirTreePreview`) y el apply operan contra
  el disco local.
- `api/devops.py:176-257` — `_load_env_context` / `/environments/plan` / `/environments/apply`
  no aceptan servidor.

### Riel existente a REUSAR (no reinventar)

- `services/remote_exec.py:158-276` — `run_remote(alias, command, *, mode, conversation_id,
  user, timeout_s)`: WinRM vía `Invoke-Command` (script `remote_exec_invoke.ps1`), credencial
  por keyring (Plan 91 `services/server_registry.py`), validador read-only endurecido
  (`is_read_only_command`, líneas 45-75: allowlist de verbos, **rechaza `{`/`}`**), auditoría
  JSONL SIEMPRE, cap de output, errores tipificados.
- `services/remote_console_prompt.py:8-45` — `build_console_prompt(server_alias, base_url,
  message, conversation_id, *, write_enabled)`: contrato de consola que instruye al agente a
  ejecutar TODO comando remoto vía `POST {base_url}/api/devops/console/exec`.
- `api/devops.py:27-60` — `_health_payload()` con paridad `/health` ↔ `/bootstrap`.

---

## 3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop:** el anclaje remoto es opt-in doble: flag global (default OFF) +
   selección explícita de servidor por el operador. El modo escritura remoto sigue gobernado
   por el toggle por-conversación del Plan 105 (default read-only). El apply de ambientes
   remoto exige el mismo `confirm=True` + `fingerprint` + `sandbox_ack` que el local.
2. **Cero trabajo extra:** sin servidor seleccionado o con la flag OFF, TODO es byte-idéntico
   a hoy. Nada de pasos manuales nuevos.
3. **Mono-operador sin auth:** `current_user()` sigue siendo el header sin validar
   (`api/_helpers.py`); no se agrega RBAC.
4. **Flags configurables desde la UI:** la flag nueva es `env_only=False`, categoría devops,
   editable desde `HarnessFlagsPanel`. Default OFF.
5. **Paridad de runtimes:** el anclaje viaja como TEXTO en el prompt ⇒ funciona idéntico en
   `claude_code_cli` y `codex_cli`. GitHub Copilot Pro conserva su degradación controlada ya
   existente (el chat DevOps rechaza runtimes no-CLI con 400 y mensaje que apunta a
   `open_chat`, `api/devops_agent.py:38-47`); el enforcement duro (read-only, auditoría) es
   server-side en `/exec`, agnóstico del runtime.
6. **No degradar:** ninguna ruta existente cambia su contrato cuando los parámetros nuevos
   están ausentes. Los fixes de RC2 solo corrigen llamadas rotas (hoy 500 incondicional).
7. **Gotchas duros del repo:** FlagSpec nueva SIN `default=` explícito (ratchet
   `_CURATED_DEFAULTS_ON`, `tests/test_harness_flags.py`); toda flag con `requires` necesita
   arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:129-138`) con
   profundidad 1 → apuntar al master `STACKY_DEVOPS_PANEL_ENABLED` (patrón Plan 107,
   `services/harness_flags.py:2209-2221`); tests nuevos registrados en
   `scripts/run_harness_tests.sh` y `.ps1` (ratchet Plan 49); mocks de imports lazy se
   parchean en el módulo ORIGEN.

---

## 4. Fases

> Comandos de test backend (SIEMPRE por archivo, venv py3.13):
> `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` y luego
> `venv\Scripts\python.exe -m pytest tests\<archivo>.py -q`
> Comandos de test frontend:
> `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` y luego
> `npx vitest run <ruta>` — más `npx tsc --noEmit` para el criterio de tipos.

---

### F0 — Reparar la consola remota del Plan 105 (bugs P0, sin flag nueva)

**Objetivo:** que crear/continuar conversaciones de consola remota funcione de verdad (hoy:
`TypeError`/`ImportError` garantizados). Es un fix de defecto bajo la flag EXISTENTE
`STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED`; no introduce flag nueva.

**Archivos a editar:**
- `Stacky Agents/backend/api/devops_remote_console.py`
- `Stacky Agents/backend/tests/test_plan105_remote_console_api.py` (corregir el mock mentiroso)

**Archivo de test nuevo:** `Stacky Agents/backend/tests/test_plan108_console_repair.py`

**Cambios exactos:**

1. En `create_conversation()` (líneas 199-227) reemplazar el bloque de lanzamiento por:

```python
    # Overrides con el MISMO clamp del plan 90 (api/devops_agent.py:48-53)
    from services import llm_router as _llm_router
    model_override = _llm_router.clamp_model(model.strip()) if model else None
    effort_override = effort.strip().lower() if effort and effort.strip().lower() in {
        "low", "medium", "high", "xhigh", "max"} else None

    from api.devops_agent import _launch_turn
    execution_id, launch_error = _launch_turn(
        conversation_id=cid,
        project=project,
        message=wrapped_message,
        runtime=runtime,
        model_override=model_override,
        effort_override=effort_override,
    )
    if launch_error is not None:
        return launch_error
    return jsonify({
        "ok": True,
        "conversation_id": cid,
        "execution_id": execution_id,
        "runtime": runtime,
        "server_alias": server_alias,
    }), 202
```

   (nota: eliminar el uso posterior de `ticket.id` fuera de sesión: usar `cid`).

2. En `conversation_message()` (líneas 230-284):
   - Eliminar `from api.devops_agent import _send_input, _launch_turn` (línea 253).
   - Leer `project`, `meta`, `server_alias`, `write_enabled` **DENTRO** del `session_scope`
     (hoy `ticket` se usa detached, líneas 246-263). Guardar en variables locales:
     `project = ticket.stacky_project_name or ticket.project`.
   - Reemplazar el "camino vivo" (`ticket.executions[-1].state == "running"`, líneas 255-258)
     por el patrón EXACTO del Plan 90 (`api/devops_agent.py:111-146`): query de
     `AgentExecution` filtrando `ticket_id == cid`, `agent_type == "devops"`, orden desc,
     leer `last.status` y `last.metadata_dict`; si `status == "running"`, importar
     `send_input` de `services.claude_code_cli_runner` o `services.codex_cli_runner` según
     `metadata_dict.get("runtime")` y llamarlo con `(last_id, message, user=current_user())`;
     ante `RuntimeError`/`ValueError` caer al camino de turno nuevo.
   - Camino de turno nuevo: misma llamada corregida del punto 1 (tupla, kwargs reales),
     con `model_override=None`, `effort_override=None`, `runtime = runtime or
     last_metadata.get("runtime") or "claude_code_cli"`.

3. En `tests/test_plan105_remote_console_api.py` (línea ~222 y cualquier otro
   `mock.patch("api.devops_agent._launch_turn", ...)`): reemplazar por
   `mock.patch("agent_runner.run_agent", return_value=101)` (se parchea el ORIGEN del efecto,
   no el contrato interno). Ajustar asserts: `execution_id == 101`.

**Tests (TDD — escribirlos primero, verlos fallar con el código actual):**

`tests/test_plan108_console_repair.py`, clase `TestPlan108ConsoleRepair`, con las flags
`STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED=True` y `STACKY_DEVOPS_SERVERS_ENABLED=True` mockeadas
(`mock.patch.object(_config.config, ...)`) y `services.server_registry.get_server` mockeado
(patrón de `tests/test_plan105_remote_console_api.py:221`):

1. `test_create_conversation_launches_real_run` — mockear `agent_runner.run_agent`
   (return 101); POST `/api/devops/console/conversations` con
   `{"server_alias":"srv1","project":"P","message":"hola"}` ⇒ 202, body
   `execution_id == 101`; assert de kwargs recibidos por `run_agent`:
   `agent_type == "devops"`, `runtime == "claude_code_cli"`.
2. `test_create_conversation_message_is_wrapped` — capturar `context_blocks` pasado a
   `run_agent`; assert `"[CONSOLA REMOTA STACKY — servidor: srv1]" in content` y
   `"hola" in content`.
3. `test_message_new_turn_when_last_completed` — sembrar Ticket consola (ado_id=-4,
   description JSON con server_alias) + AgentExecution `status="completed"`; POST
   `/conversations/<cid>/message` ⇒ 200/202 y `run_agent` llamado 1 vez.
4. `test_message_live_uses_runner_send_input` — sembrar AgentExecution `status="running"`,
   `metadata_dict={"runtime":"claude_code_cli"}`; mockear
   `services.claude_code_cli_runner.send_input` (ORIGEN, gotcha lazy import) return
   `{"mode":"stdin"}`; POST message ⇒ 200 y `send_input` llamado con `(exec_id, "texto")`.
5. `test_source_has_no_send_input_import` — leer el archivo fuente
   `api/devops_remote_console.py` (`pathlib.Path(...).read_text(encoding="utf-8")`) y assert
   `"_send_input" not in source` y `"ticket_id=" not in source` (centinela anti-regresión de
   la firma rota).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan108_console_repair.py -q`
y re-correr `venv\Scripts\python.exe -m pytest tests\test_plan105_remote_console_api.py -q`.

**Criterio binario:** ambos archivos 100% verdes; los 5 tests nuevos FALLABAN antes del fix
(obligatorio verificar el rojo inicial con el test 1 y 5 como mínimo).

**Flag:** la existente `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED` (OFF default). Sin flag nueva.
**Runtimes:** claude_code_cli/codex_cli reparados; Copilot sin cambios (nunca entra: 400).
**Trabajo del operador:** ninguno.

---

### F1 — Flag `STACKY_DEVOPS_REMOTE_TARGET_ENABLED` + health/bootstrap

**Objetivo:** gate único, visible en UI, para "operar sobre el servidor seleccionado"
(chat del agente y ambientes).

**Archivos a editar:**
- `Stacky Agents/backend/config.py` — junto a las flags devops (patrón líneas 886-947):

```python
    STACKY_DEVOPS_REMOTE_TARGET_ENABLED: bool = os.getenv(
        "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", "false"
    ).lower() == "true"
```

- `Stacky Agents/backend/services/harness_flags.py` —
  1. agregar `"STACKY_DEVOPS_REMOTE_TARGET_ENABLED",  # Plan 108 — agente/ambientes operan en el servidor seleccionado`
     a la lista de la categoría devops (junto a línea ~192);
  2. FlagSpec nueva copiando el patrón EXACTO de líneas 2209-2221:
     `key="STACKY_DEVOPS_REMOTE_TARGET_ENABLED"`, `type="bool"`,
     `label="Operar en el servidor seleccionado (Plan 108)"`,
     `description="Plan 108 — Ancla el chat del agente DevOps y el plan/apply de Ambientes al servidor seleccionado en el panel: exploración y comandos corren vía WinRM auditado (Plan 105), nunca en la máquina local. Requiere Servidores (91) y Consola remota (105) activos. Default OFF."`,
     `group="global"`, `env_only=False`,
     `requires="STACKY_DEVOPS_PANEL_ENABLED"`, **SIN `default=`**.
- `Stacky Agents/backend/services/harness_flags_help.py` — entrada de ayuda "para mortales"
  (patrón de las flags del Plan 107 en ese archivo).
- `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar la arista
  `"STACKY_DEVOPS_REMOTE_TARGET_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 108`
  a `_REQUIRES_MAP_FROZEN` (líneas 129-138).
- `Stacky Agents/backend/api/devops.py` — en `_health_payload()` (líneas 37-60) agregar:
  `"remote_target_enabled": bool(getattr(cfg, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False)),  # Plan 108`
  (la paridad `/bootstrap` es automática: comparte `_health_payload`).

**Archivo de test nuevo:** `Stacky Agents/backend/tests/test_plan108_flags.py`
1. `test_flag_default_off` — `config.STACKY_DEVOPS_REMOTE_TARGET_ENABLED is False` sin env var.
2. `test_flag_registered_devops_category` — el registry contiene la key en categoría devops.
3. `test_flag_requires_panel_master` — `spec.requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
4. `test_health_exposes_remote_target` — GET `/api/devops/health` ⇒ key
   `remote_target_enabled` presente, `False` por default.
5. `test_flag_editable_from_ui` — `spec.env_only is False`.

**Comandos:**
`venv\Scripts\python.exe -m pytest tests\test_plan108_flags.py -q`
`venv\Scripts\python.exe -m pytest tests\test_harness_flags.py -q`
`venv\Scripts\python.exe -m pytest tests\test_harness_flags_requires.py -q`

**Criterio binario:** los 3 archivos verdes (el de requires puede arrastrar el drift
preexistente documentado de `harness_defaults.env` — si un test centinela ajeno ya estaba en
rojo ANTES de esta fase, documentarlo con `git stash` como baseline y no contarlo como
regresión propia).

**Flag:** `STACKY_DEVOPS_REMOTE_TARGET_ENABLED` (default OFF, UI-editable).
**Runtimes:** N/A (infra). **Trabajo del operador:** opt-in (default off).

---

### F2 — Endurecer el contrato del prompt: prohibición explícita de tools locales

**Objetivo:** que el agente CLI no pueda "interpretar" que sus herramientas locales sirven
para responder sobre el servidor.

**Archivo a editar:** `Stacky Agents/backend/services/remote_console_prompt.py`

**Cambio exacto:** en `build_console_prompt` (misma firma, sin parámetros nuevos), insertar
en la sección `Reglas:` (después de la regla 1, renumerando el resto) la regla:

```
2. PROHIBIDO usar tus herramientas locales (shell local, listado/lectura de archivos de esta
   máquina, Bash, PowerShell local) para responder CUALQUIER cosa sobre el servidor
   "{server_alias}". Esta máquina NO es el servidor. Toda exploración de directorios,
   lectura de archivos y ejecución en el servidor pasa EXCLUSIVAMENTE por el endpoint
   /api/devops/console/exec de arriba. Si un comando remoto falla, informalo; NUNCA lo
   "simules" localmente.
```

**Archivo de test nuevo:** `Stacky Agents/backend/tests/test_plan108_prompt_hardening.py`
1. `test_prompt_prohibits_local_tools` — el string devuelto contiene
   `"PROHIBIDO usar tus herramientas locales"` y `"Esta máquina NO es el servidor"`.
2. `test_prompt_keeps_exec_contract` — sigue conteniendo
   `"/api/devops/console/exec"` y el `server_alias` interpolado (no-regresión del Plan 105 F3).
3. `test_prompt_write_mode_text_unchanged` — con `write_enabled=True` contiene
   `"LECTURA+ESCRITURA"`; con `False` contiene `"SOLO LECTURA"`.

**Comandos:**
`venv\Scripts\python.exe -m pytest tests\test_plan108_prompt_hardening.py -q`
`venv\Scripts\python.exe -m pytest tests\test_plan105_console_prompt.py -q`

**Criterio binario:** ambos archivos verdes.
**Flag:** sin flag (texto del contrato; solo se emite en flujos ya gateados).
**Runtimes:** texto ⇒ paridad total claude/codex; Copilot no recibe este prompt (degradación
ya existente). **Trabajo del operador:** ninguno.

---

### F3 — Backend: el chat del agente DevOps acepta `server_alias` y ancla el turno

**Objetivo:** cerrar RC1 en el backend: si llega `server_alias`, el turno viaja envuelto con
el contrato de consola remota y la conversación queda sellada a ese servidor.

**Archivo a editar:** `Stacky Agents/backend/api/devops_agent.py`

**Cambios exactos:**

1. Agregar helper module-level (copiado del patrón `_conv_meta`,
   `api/devops_remote_console.py:38-46` — se duplica adrede para no crear import circular):

```python
def _chat_meta(ticket) -> dict:
    """description es JSON {"kind":"devops_chat","server_alias":str} o {}. Tolerante."""
    import json
    if not ticket or not ticket.description:
        return {}
    try:
        return json.loads(ticket.description) if isinstance(ticket.description, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
```

2. Agregar helper de validación:

```python
def _validate_remote_target(server_alias: str):
    """None si OK; (json_response, status) si no. Gates: flag 108 + servers 91 + consola 105
    + alias existente en el registro."""
    cfg = _config.config
    if not getattr(cfg, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False):
        return jsonify({"ok": False, "error": "remote_target_disabled"}), 400
    if not getattr(cfg, "STACKY_DEVOPS_SERVERS_ENABLED", False) or \
       not getattr(cfg, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False):
        return jsonify({"ok": False, "error": "remote_target_requires_servers_and_console"}), 409
    from services.server_registry import get_server
    try:
        get_server(server_alias)
    except Exception:
        return jsonify({"ok": False, "error": "server_not_found"}), 404
    return None
```

3. En `start_conversation()` (después de validar runtime, línea ~47):
   - `server_alias = (body.get("server_alias") or "").strip() or None`
   - si `server_alias`: `err = _validate_remote_target(server_alias)`; `if err: return err`.
   - Al crear el Ticket (líneas 70-77) agregar
     `description=json.dumps({"kind": "devops_chat", "server_alias": server_alias}) if server_alias else None`.
   - Antes de `_launch_turn`, si `server_alias`:

```python
        from services.remote_console_prompt import build_console_prompt
        base_url = request.host_url.rstrip("/")
        message = build_console_prompt(
            server_alias, base_url, message, conversation_id, write_enabled=False,
        )
```

   - Incluir `"server_alias": server_alias` en el JSON de respuesta 202.

4. En `send_message()` (líneas 102-163): dentro del `session_scope` existente leer
   `server_alias = _chat_meta(ticket).get("server_alias")`. En el camino de turno nuevo
   (camino 2, líneas 148-160), si `server_alias` es truthy Y
   `getattr(_config.config, "STACKY_DEVOPS_REMOTE_TARGET_ENABLED", False)`, envolver
   `message` con `build_console_prompt(server_alias, request.host_url.rstrip("/"), message,
   conversation_id, write_enabled=False)` antes de `_launch_turn`. El camino vivo (stdin,
   líneas 131-146) envía el texto crudo SIN envolver (el contrato ya vive en la sesión del
   CLI; envolver cada stdin duplicaría el header — decisión idéntica al Plan 105).

5. En `list_conversations()` (items, líneas 200-214) agregar
   `"server_alias": _chat_meta(t).get("server_alias"),`.

**Archivo de test nuevo:** `Stacky Agents/backend/tests/test_plan108_agent_server_binding.py`
(todas con `STACKY_DEVOPS_AGENT_ENABLED=True` mockeada; mockear `agent_runner.run_agent`
return 77 — NUNCA `_launch_turn`):
1. `test_start_without_alias_unchanged` — POST sin `server_alias` ⇒ 202; el content del
   `context_blocks` capturado NO contiene `"CONSOLA REMOTA"` (byte-compat).
2. `test_start_with_alias_flag_off_400` — `server_alias="srv1"` con
   `STACKY_DEVOPS_REMOTE_TARGET_ENABLED=False` ⇒ 400 `remote_target_disabled`.
3. `test_start_with_alias_deps_off_409` — flag 108 ON pero
   `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED=False` ⇒ 409.
4. `test_start_with_alias_unknown_404` — `get_server` mock lanza `KeyError` ⇒ 404.
5. `test_start_with_alias_wraps_and_seals` — flags ON + `get_server` OK ⇒ 202; content
   capturado contiene `"[CONSOLA REMOTA STACKY — servidor: srv1]"` y
   `"PROHIBIDO usar tus herramientas locales"`; el Ticket creado tiene
   `description` JSON con `server_alias == "srv1"`; respuesta incluye `server_alias`.
6. `test_send_message_new_turn_rewraps` — sembrar ticket ado_id=-2 con description sellada +
   AgentExecution `completed`; POST message ⇒ el nuevo content contiene el header de consola.
7. `test_list_conversations_exposes_alias` — GET lista ⇒ item con `server_alias == "srv1"`.

**Comandos:**
`venv\Scripts\python.exe -m pytest tests\test_plan108_agent_server_binding.py -q`
`venv\Scripts\python.exe -m pytest tests\test_plan90_devops_agent_endpoints.py -q` (no-regresión)

**Criterio binario:** ambos verdes; test 1 garantiza byte-compat sin alias.
**Flag:** `STACKY_DEVOPS_REMOTE_TARGET_ENABLED` (OFF ⇒ 400 si se intenta usar).
**Runtimes:** claude/codex paridad total (contrato textual); Copilot: `start_conversation`
ya rechaza runtimes no-CLI con 400 (`devops_agent.py:38-47`) — degradación explícita intacta.
**Trabajo del operador:** opt-in (flag + seleccionar servidor).

---

### F4 — Frontend: el chat consume `ctx.selectedServer` (badge + envío del alias)

**Objetivo:** cerrar RC1 en la UI: el chat muestra DÓNDE va a operar el agente y envía el alias.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — en `DevOpsAgentApi.start` (línea ~3175-3186):
  ampliar el payload tipado a
  `{ project: string; message: string; runtime?: string; server_alias?: string }`
  (el body se pasa tal cual; sin cambios de URL).
- **Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/agentServerBinding.ts` —
  helper PURO (testeable sin jsdom/RTL, gap conocido del repo):

```ts
export interface AgentServerBinding {
  sendAlias: string | null;   // alias a incluir en el POST, o null
  badge: string | null;       // texto del badge, o null si no se muestra
  hint: string | null;        // aviso si hay server seleccionado pero falta una flag
}

export function resolveAgentServerBinding(
  health: { remote_target_enabled?: boolean; servers_enabled?: boolean; remote_console_enabled?: boolean },
  selectedServer: { alias: string; host: string } | null | undefined,
): AgentServerBinding {
  if (!selectedServer) return { sendAlias: null, badge: null, hint: null };
  const ready = health.remote_target_enabled === true
    && health.servers_enabled === true
    && health.remote_console_enabled === true;
  if (!ready) {
    return {
      sendAlias: null, badge: null,
      hint: `Servidor "${selectedServer.alias}" seleccionado, pero el agente operará LOCAL: ` +
        `activá "Operar en el servidor seleccionado" (y Servidores + Consola remota) en el Arnés.`,
    };
  }
  return {
    sendAlias: selectedServer.alias,
    badge: `Ejecutando EN ${selectedServer.alias} (${selectedServer.host})`,
    hint: null,
  };
}
```

- `Stacky Agents/frontend/src/components/devops/DevOpsAgentSection.tsx`:
  1. `const binding = resolveAgentServerBinding(ctx.health, ctx.selectedServer);`
  2. En el mutation de start (línea ~65) pasar
     `...(binding.sendAlias ? { server_alias: binding.sendAlias } : {})`.
  3. Render: si `binding.badge`, mostrar un `<span>` con clase existente de badge de
     `devops.module.css` y el texto del badge; si `binding.hint`, mostrar un aviso
     (mismo patrón visual que `FlagGateBanner.tsx`). Sin servidor: cero cambios visuales.
  4. En la lista de conversaciones, si el item trae `server_alias`, prefijar el título con
     `[{server_alias}] `.
- Tipos: agregar `remote_target_enabled?: boolean` al tipo del health devops y
  `server_alias?: string` al item de conversación donde estén definidos (buscar el tipo del
  health en `frontend/src` con grep de `remote_console_enabled` y extenderlo ahí mismo).

**Archivo de test nuevo:**
`Stacky Agents/frontend/src/components/devops/__tests__/agentServerBinding.test.ts`
(patrón del repo: `__tests__/PipelineBuilderSection.test.ts`, lógica pura sin RTL):
1. `sin servidor ⇒ {null, null, null}`.
2. `servidor + las 3 flags ON ⇒ sendAlias y badge correctos`.
3. `servidor + remote_target OFF ⇒ sendAlias null y hint no nulo`.
4. `servidor + remote_target ON pero console OFF ⇒ hint no nulo`.

**Comandos:**
`npx vitest run src/components/devops/__tests__/agentServerBinding.test.ts`
`npx tsc --noEmit`

**Criterio binario:** vitest 4/4 verde y `tsc --noEmit` con 0 errores.
**Flag:** gobernado por el health (F1); con flag OFF la UI solo muestra el hint (opt-in).
**Runtimes:** N/A (UI). **Trabajo del operador:** ninguno adicional (usa la selección que ya hace).

---

### F5 — Backend: plan/apply de Ambientes contra el servidor (cierra RC3)

**Objetivo:** que `/environments/plan` y `/environments/apply` (y por lo tanto el preview de
árbol del Plan 107) evalúen y creen carpetas EN el servidor cuando llega `server_alias`.

**Archivo NUEVO:** `Stacky Agents/backend/services/environment_remote.py`

Funciones exactas (todas puras salvo las dos que llaman `run_remote`):

```python
import ntpath

_CHUNK = 50  # paths por comando remoto (límite de longitud de línea)

def _q(path: str) -> str:
    """Escapa comillas simples PowerShell: ' -> ''. Retorna 'path' entre comillas simples."""

def build_remote_status_command(abs_paths: list[str]) -> str:
    """Por cada path emite DOS statements separados por ';':
    Test-Path -LiteralPath '<p>'  y  Test-Path -LiteralPath '<p>' -PathType Container.
    SIN llaves ni loops (el validador read-only rechaza '{'/'}',
    services/remote_exec.py:52-56). El comando resultante DEBE pasar
    is_read_only_command() — test obligatorio."""

def parse_status_output(stdout: str, abs_paths: list[str]) -> list[dict]:
    """stdout = líneas True/False en pares por path (en orden). Retorna
    [{'path': p, 'exists': bool, 'is_dir': bool}]. Si el número de líneas no es
    2*len(abs_paths) ⇒ ValueError('remote_status_parse_error')."""

def build_remote_mkdir_command(abs_paths: list[str]) -> str:
    """'New-Item -ItemType Directory -Force -LiteralPath <p> | Out-Null' unidos por ';'."""

def resolve_remote_layout(root: str, rel_paths: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """PURA, con ntpath (el server es Windows; run_remote es win-only,
    services/remote_exec.py:193). Por cada rel: final = ntpath.normpath(ntpath.join(root, rel)).
    'unsafe' si el final no queda BAJO root (comparación textual case-insensitive con
    ntpath.normcase + prefijo root + separador — mismo espíritu del guard local de
    environment_init.plan_environment, sin realpath porque no hay fs local).
    Retorna ([(rel, final_abs)] seguros, [rel] unsafe)."""

def plan_environment_remote(alias: str, root: str, rel_paths: list[str],
                            *, conversation_id=None, user: str = "") -> dict:
    """1) resolve_remote_layout. 2) probes en chunks de _CHUNK vía
    services.remote_exec.run_remote(alias, cmd, mode='read_only', user=user)
    (primero un probe del root solo). 3) Mapear al MISMO shape del plan local
    (environment_init.plan_environment): {'root','root_exists','entries':[{'rel','final',
    'status'}],'summary':{...}} + {'remote': True, 'server_alias': alias}.
    status: 'to_create' si not exists; 'exists_ok' si is_dir; 'conflict' si exists y no
    is_dir; 'unsafe' para los descartados. Si run_remote devuelve ok=False ⇒ retornar
    {'ok': False, 'error': result['error'], 'remote': True} SIN inventar estados."""

def apply_environment_remote(alias: str, root: str, approved_abs: list[str],
                             *, conversation_id=None, user: str = "") -> dict:
    """mkdir en chunks vía run_remote(mode='write') + verificación posterior con los mismos
    probes read_only. Retorna {'created': [...], 'errors': [...], 'remote': True}.
    NUNCA borra nada (paridad con apply_environment local, environment_init.py:4)."""
```

**Archivo a editar:** `Stacky Agents/backend/api/devops.py`
- `_load_env_context` (líneas 176-211): además retornar `server_alias` leído de
  `body.get("server_alias")` (string o None) SIN validarlo ahí (tupla pasa a 4 elementos:
  `(root, rel_paths, sandbox_active, server_alias)`; actualizar los 2 call sites).
- `environment_plan_route` (líneas 214-224): si `server_alias`:
  - Reusar `_validate_remote_target` (import desde `api.devops_agent`) ⇒ mismos 400/409/404.
  - `result = plan_environment_remote(server_alias, root, rel_paths, user=current_user())`.
  - Si el dict trae `"ok": False` ⇒ status 502 (mapa de errores del Plan 105:
    `keyring_unavailable`/`no_password` ⇒ 503, `server_not_found` ⇒ 404, `timeout` ⇒ 504,
    resto 502 — copiar el mapeo de `api/devops_remote_console.py:95-108`).
  - `result["sandbox_active"] = sandbox_active` igual que hoy.
- `environment_apply_route` (líneas 227-257): mismo gate; el `fingerprint` se calcula igual
  (`layout_fingerprint(root, rel_paths)` es puro sobre strings — sirve idéntico);
  `approved` se traduce a paths absolutos con `resolve_remote_layout` y se llama
  `apply_environment_remote(...)`. HITL intacto: `confirm=True` + `fingerprint` +
  (`sandbox_ack` si hay `root_override`).

**Archivo de test nuevo:** `Stacky Agents/backend/tests/test_plan108_environment_remote.py`
1. `test_status_command_is_read_only` — `build_remote_status_command([r"D:\Apps\a", r"D:\Apps\o'brien"])`
   pasa `services.remote_exec.is_read_only_command` y contiene `''` (quote escapado).
2. `test_status_command_has_no_braces` — `"{" not in cmd and "}" not in cmd`.
3. `test_parse_status_output_pairs` — stdout `"True\nTrue\nTrue\nFalse\nFalse\nFalse\n"`
   para 3 paths ⇒ exists/is_dir correctos; líneas de más ⇒ `ValueError`.
4. `test_resolve_remote_layout_unsafe` — rel `"..\\fuera"` cae en unsafe; rel normal produce
   `ntpath` join correcto.
5. `test_plan_remote_maps_statuses` — mockear `services.remote_exec.run_remote` (ORIGEN)
   devolviendo stdout simulado ⇒ summary `{to_create:1, exists_ok:1, conflict:1}` según el
   fixture; `result["remote"] is True`.
6. `test_plan_remote_propagates_error` — `run_remote` ok=False error="no_password" ⇒
   `{'ok': False, 'error': 'no_password'}` (sin estados inventados).
7. `test_apply_remote_uses_write_mode_and_verifies` — capturar kwargs de `run_remote`:
   primer call `mode="write"`, verificación posterior `mode="read_only"`.
8. `test_endpoint_plan_with_alias_gates` — POST `/api/devops/environments/plan` con
   `server_alias` y flag 108 OFF ⇒ 400; con flags ON + mocks ⇒ 200 y `remote: True`.
9. `test_endpoint_without_alias_byte_identical` — sin `server_alias`, con la flag 108 ON,
   la respuesta es la del camino local de siempre (sin key `remote`).

**Comandos:**
`venv\Scripts\python.exe -m pytest tests\test_plan108_environment_remote.py -q`
`venv\Scripts\python.exe -m pytest tests\test_plan89_environment_plan_apply.py -q`
`venv\Scripts\python.exe -m pytest tests\test_plan89_environments_endpoints.py -q`
`venv\Scripts\python.exe -m pytest tests\test_plan107_sandbox_endpoints.py -q`

**Criterio binario:** los 4 archivos verdes; test 9 garantiza el byte-compat local.
**Flag:** `STACKY_DEVOPS_REMOTE_TARGET_ENABLED` + dependencias 91/105 (gates de
`_validate_remote_target`).
**Runtimes:** N/A (server-side puro; no toca runtimes de agentes).
**Trabajo del operador:** opt-in; el sandbox del Plan 107 sigue funcionando igual en ambos
modos (el guard `validate_sandbox_override` es textual y se aplica ANTES, `devops.py:193-203`).

---

### F6 — Frontend: Ambientes contra el servidor (badge + `server_alias` en plan/apply)

**Objetivo:** que la sección Ambientes (Plan 89/107) muestre dónde opera y envíe el alias.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — los métodos de plan/apply de environments
  (buscar `environments/plan` en el archivo) aceptan `server_alias?: string` en el body.
- `Stacky Agents/frontend/src/components/devops/EnvironmentsSection.tsx`:
  1. Reusar `resolveAgentServerBinding(ctx.health, ctx.selectedServer)` (F4) — mismo helper,
     cero lógica nueva.
  2. Si `binding.sendAlias`: incluir `server_alias` en los POST de plan y apply, y renderizar
     el badge `Ejecutando EN <alias>` junto al root; si `binding.hint`, mostrar el aviso.
  3. Si la respuesta de plan trae `remote: true`, mostrar la palabra `remoto` en el resumen
     del plan (texto plano, sin estilos nuevos).
  4. Sin servidor seleccionado: cero cambios (byte-compat).

**Tests:** el helper ya quedó cubierto en F4 (lógica pura compartida). Agregar 1 caso a
`agentServerBinding.test.ts`: `5. el mismo binding sirve para Ambientes (no depende de la
sección)` — smoke que fija el contrato del tipo.
**Comandos:** `npx vitest run src/components/devops/__tests__/agentServerBinding.test.ts` y
`npx tsc --noEmit`.

**Criterio binario:** vitest 5/5 y tsc 0 errores.
**Flag/operador/runtimes:** igual que F4.

---

### F7 — Cierre: ratchet, export de defaults, doc y no-regresión

**Objetivo:** dejar el plan auditable y sin drift.

**Pasos exactos:**
1. Registrar los 5 archivos de test backend nuevos en
   `Stacky Agents/backend/scripts/run_harness_tests.sh` **y**
   `Stacky Agents/backend/scripts/run_harness_tests.ps1` (ratchet del Plan 49; si falta uno,
   el meta-test lo detecta):
   `test_plan108_console_repair.py`, `test_plan108_flags.py`,
   `test_plan108_prompt_hardening.py`, `test_plan108_agent_server_binding.py`,
   `test_plan108_environment_remote.py`.
2. Regenerar `Stacky Agents/backend/harness_defaults.env` con el generador REAL
   `deployment/export_harness_defaults.py` (NO editar a mano; gotcha del drift 87-91).
3. Actualizar el encabezado de ESTE doc a IMPLEMENTADO con el detalle de fases/tests
   (regla de la casa: el estado vive en el doc).
4. No-regresión (por archivo, en este orden):
   `test_plan90_devops_agent_endpoints.py`, `test_plan90_devops_agent_flag.py`,
   `test_plan105_remote_console_api.py`, `test_plan105_remote_exec_service.py`,
   `test_plan105_console_prompt.py`, `test_plan89_environment_plan_apply.py`,
   `test_plan89_environments_endpoints.py`, `test_plan107_sandbox_endpoints.py`,
   `test_plan107_flags.py`, `test_harness_flags.py`, `test_harness_flags_requires.py`.
5. Frontend: `npx tsc --noEmit` (0 errores) + vitest de F4/F6.

**Criterio binario:** todos los comandos anteriores verdes (o rojo PREEXISTENTE demostrado
contra `git stash` y documentado como drift ajeno, nunca silenciado).
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El agente CLI ignora el contrato del prompt y usa tools locales igual | F2 endurece la prohibición en texto explícito; el enforcement DURO (read-only, credenciales, auditoría) ya es server-side en `/exec` — el agente jamás tiene la credencial. Riesgo residual: respuestas basadas en disco local — mitigado por el badge de la UI (el operador VE dónde opera) y la auditoría (0 entradas = sospecha). |
| Longitud de comando WinRM con muchos paths | Chunks de 50 paths (`_CHUNK`) en `environment_remote.py`. |
| `Test-Path` par desalineado (output corrupto) | `parse_status_output` valida `2*len(paths)` líneas y falla ruidoso (`remote_status_parse_error`), nunca inventa estados. |
| Regresión del chat local (Plan 90) | Test F3-1 `test_start_without_alias_unchanged` + suite plan 90 completa en F7. |
| Falso verde estilo Plan 105 (mock de símbolo interno) | Regla codificada en F0/F3: PROHIBIDO mockear `_launch_turn`; se mockea `agent_runner.run_agent` (origen). Centinela F0-5 lee el fuente. |
| Import circular `devops_agent` ↔ `devops_remote_console` | `_chat_meta` se duplica en `devops_agent.py` (8 líneas, documentado); `_validate_remote_target` vive en `devops_agent.py` y lo importa `devops.py` (dirección nueva, sin ciclo). |
| Drift `harness_defaults.env` | F7 paso 2 usa el generador real de `deployment/`. |

## 6. Fuera de scope

- SSH/Linux como transporte remoto (el riel 105 es WinRM win32-only; `remote_exec_windows_only` ya degrada explícito).
- Ejecutar el RUNTIME CLI (claude/codex) físicamente dentro del servidor (instalación de CLIs remotas): el modelo es "agente local, manos remotas vía /exec".
- Modo escritura remoto para el chat DevOps anclado (arranca `write_enabled=False` fijo; el toggle por conversación del Plan 105 queda para la consola).
- Publicaciones/pipelines remotos (Planes 88/93-96 no cambian).
- Multi-servidor por conversación (1 conversación = 1 alias sellado).

## 7. Glosario

- **Alias / registro de servidores:** nombre corto de un servidor registrado (Plan 91,
  `services/server_registry.py`) con host + credencial en keyring de Windows.
- **Consola remota (`/exec`):** endpoint `POST /api/devops/console/exec` (Plan 105) que ejecuta
  UN comando PowerShell en el servidor del alias vía WinRM, con validador read-only y auditoría.
- **`_launch_turn`:** función interna del Plan 90 (`api/devops_agent.py:219`) que lanza un turno
  del agente DevOps como ejecución del harness (`agent_runner.run_agent`). Retorna
  `(execution_id, None)` o `(None, respuesta_flask_de_error)`.
- **Anclaje remoto:** sellar una conversación del agente a un `server_alias`: cada turno viaja
  envuelto por `build_console_prompt`, que obliga al agente a operar vía `/exec`.
- **Sandbox de ambientes (Plan 107):** raíz alternativa transitoria para probar el plan/apply
  sin tocar producción; guard `validate_sandbox_override` (textual, sirve igual en remoto).
- **Ratchet de tests:** los archivos de test backend nuevos DEBEN listarse en
  `scripts/run_harness_tests.sh/.ps1` o un meta-test falla (Plan 49).
- **R4 profundidad-1:** toda flag con `requires` apunta directo a una flag master (sin cadenas)
  y necesita su arista en `_REQUIRES_MAP_FROZEN`.

## 8. Orden de implementación

1. F0 (reparación consola 105 — desbloquea todo lo demás)
2. F1 (flag + health)
3. F2 (prompt endurecido)
4. F3 (backend chat binding)
5. F4 (frontend chat)
6. F5 (backend ambientes remoto)
7. F6 (frontend ambientes)
8. F7 (cierre)

## 9. Definición de Hecho (DoD)

- [ ] Los 5 archivos `test_plan108_*.py` verdes por archivo con el venv del repo.
- [ ] `test_plan105_remote_console_api.py` verde SIN ningún mock de `_launch_turn`.
- [ ] Vitest `agentServerBinding.test.ts` 5/5 y `tsc --noEmit` 0 errores.
- [ ] Suites de no-regresión de F7 verdes (o rojo preexistente demostrado con `git stash`).
- [ ] Con `STACKY_DEVOPS_REMOTE_TARGET_ENABLED=false` (default): TODO byte-idéntico a HEAD.
- [ ] Flag visible y editable en la UI del Arnés (env_only=False), default OFF.
- [ ] `harness_defaults.env` regenerado con `deployment/export_harness_defaults.py`.
- [ ] Encabezado de este doc actualizado al estado real.
- [ ] Push manual del operador (NUNCA automático).
