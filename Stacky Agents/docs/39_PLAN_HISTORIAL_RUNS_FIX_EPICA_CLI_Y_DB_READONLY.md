# Plan 39 — Historial de ejecuciones completo + Fix 500 al crear Épica con Claude CLI + Fix DB con usuario read-only del perfil

> Estado: PROPUESTO. Numeración: **39** (consecutiva; máximo previo real en `Stacky Agents/docs/` = `38_PLAN_VERSION_EPICA_BRIEF_TRAZABILIDAD.md`. La secuencia es compartida planes/checklists/incidentes; 39 es el siguiente libre sin huecos).
> Autor: StackyArchitectaUltraEficientCode.
> Audiencia: dev agéntico junior / modelo menor (Haiku, Codex CLI, GitHub Copilot Pro). **Cada fase es autocontenida**: objetivo, evidencia `archivo:línea`, archivos exactos, símbolos exactos, pseudocódigo, tests primero, comando exacto, criterio binario, flag + default, impacto por runtime y línea "Trabajo del operador".
> Pensado para implementarse SIN inferir nada. Prohibido lo vago.
> Los TRES bloques (A, B, C) son independientes entre sí; dentro de cada bloque las fases van en orden de dependencia.

---

## 1. Título, objetivo y KPI

**Objetivo.** Cerrar tres incidencias del operador reusando lo que ya existe, sin agregar trabajo manual:

- **Bloque A — Historial de ejecuciones completo.** Una vista de historial donde, por cada run, se ve: tiempo (duración + inicio/fin), prompt(s) usado(s), resultado/estado, costo, modelo, runtime y agente. El backend YA persiste casi todo (Plan 38 Bloque C dejó `prompt_sha`/`agent_type`/`produced_files` en `metadata`; el costo y el modelo ya existen en columnas/metadata). El gap es: (1) un endpoint de listado enriquecido y filtrable, y (2) una página de historial en el frontend que lo muestre completo. Cero captura nueva de datos por run salvo asegurar la duración.
- **Bloque B — Fix bug 500 al crear Épica con runtime `claude_code_cli`.** Diagnóstico con evidencia + fix. Causa raíz arquitectónica confirmada: el endpoint `POST /api/agents/run-brief` (`backend/api/agents.py:544`) solo captura `agent_runner.UnknownAgentError`; cualquier OTRA excepción de `agent_runner.run_agent(...)` (que para `claude_code_cli` entra a `_start_cli_runtime`, `agent_runner.py:140-151`) burbujea sin manejo → Flask responde **500 `Internal server error`** con `request_id`. La causa específica (qué falla dentro de `_start_cli_runtime` con el "Brief Pool Ticket" `ado_id=-1`) se reproduce capturando el traceback real (Fase B0) antes de fijar el fix.
- **Bloque C — Fix funcional: el agente NO usa el usuario read-only del perfil al acceder a la DB de RSPACIFICO.** Diagnóstico con evidencia + fix. Evidencia: el default del perfil trae `database.connection_kind="windows_sqlcmd"` y `database.readonly_user_hint=""` (`backend/services/client_profile_default_templates.py:52-53`); el `Developer.agent.md` instruye al agente a NO usar el password del perfil y a emitir SQL para que el operador lo ejecute (`Developer.agent.md:104`), pero el único consumidor de la credencial cifrada (`auth/db_readonly.json`) es `services/db_query.py`, que **es un stub que NO ejecuta la query** (`db_query.py:14-27, 277`). Resultado: cuando el agente conecta a la BD por su cuenta usa `sqlcmd` con autenticación integrada de Windows (el usuario de la máquina), nunca el usuario read-only del perfil. El fix hace que el usuario read-only sea la fuente de verdad inyectada al agente y bloquea/ desaconseja la auth integrada cuando hay credencial read-only configurada.

**KPI / impacto.**
- KPI-A1 (binario): `GET /api/executions/history` devuelve, para el 100% de las ejecuciones nuevas, los campos `duration_ms`, `model`, `runtime`, `agent_type`, `status`, `cost_usd` (puede ser `null`), `prompt_sha` (o `prompt_text` si flag) — todos presentes como claves.
- KPI-A2 (operador): el tiempo de "¿cuánto tardó / qué modelo / cuánto costó / qué prompt usó esta ejecución?" pasa de leer logs crudos o varias vistas a **una sola tabla de historial filtrable**.
- KPI-B1 (binario): crear una Épica desde brief con runtime `claude_code_cli` ya **no** devuelve HTTP 500 genérico. Si hay un error real, devuelve HTTP 4xx/202 con un mensaje accionable (no `Internal server error`).
- KPI-B2 (binario): el flujo "brief → BusinessAgent (claude_code_cli) → Épica" se completa de punta a punta en una verificación manual sobre un proyecto real.
- KPI-C1 (binario): cuando el proyecto tiene `auth/db_readonly.json` configurado, el contexto inyectado al agente y/o el endpoint `db_query` resuelven `user` == el usuario read-only del perfil (NO vacío, NO Windows-auth), verificado por test.
- KPI-C2 (binario): si hay credencial read-only configurada, el agente NO recibe instrucción de usar autenticación integrada de Windows; recibe explícitamente el usuario read-only a usar.

---

## 2. Por qué ahora / gap que cierra

Apoyado en los planes recientes leídos (38 versión/épica/trazabilidad, 34 client-profile, 36 selector-runtime, 33 flags-UI):

- **Bloque A.** El Plan 38 Bloque C ya persiste prompt/agente/archivos en `AgentExecution.metadata_json` y los muestra en el **drawer de detalle de UNA ejecución** (`ExecutionDetailDrawer.tsx`). Falta la vista **agregada de historial**: una tabla de TODOS los runs con sus columnas clave (tiempo, modelo, costo, resultado, prompt). El endpoint de listado actual `GET /api/executions` (`backend/api/executions.py:26`) devuelve `to_dict(include_output=False)` pero no garantiza ni expone de forma uniforme duración/costo/modelo para una vista de historial. Este bloque agrega un endpoint enriquecido y la página, **reusando** lo que el 38 ya guarda.
- **Bloque B.** El endpoint `run-brief` se agregó en el Plan 38 (`agents.py:544`) y su único `except` es `UnknownAgentError`. El Plan 36/37 dejó claro que `claude_code_cli` es un runtime de primera clase (no bloqueado). Por lo tanto el brief CON claude_code_cli ejecuta `_start_cli_runtime`, y cualquier fallo de preparación (pool ticket `ado_id=-1`, output dir, sesión claude no logueada) explota como 500. Es un bug real y reciente.
- **Bloque C.** El sustrato de credencial read-only (`auth/db_readonly.json` + `_resolve_db_readonly`, `db_query.py:194-220`) existe desde el Plan 16, pero (a) el endpoint que lo usa es un stub que no ejecuta, y (b) el agente, guiado por el `.agent.md` y por `connection_kind="windows_sqlcmd"`, termina usando Windows-auth. El Plan 34 (D2/D7) ya identificó que el default está contaminado y que `readonly_user_hint` es de bajo valor; este plan cierra el lazo: el usuario read-only debe ser lo que el agente use, de forma inyectada y verificable.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cada ítem funciona en los 3 o degrada con fallback **explícito**. Nada atado a un runtime.
- **Cero trabajo extra del operador:** invisible/automático u opt-in con default seguro. Backward-compatible. Ninguna carga de config nueva obligatoria.
- **Human-in-the-loop innegociable:** no se agrega autonomía. El historial es lectura; los fixes no cambian decisiones del operador.
- **Mono-operador sin auth real:** nada de RBAC ni multiusuario.
- **No degradar** performance/seguridad/estabilidad/DX. Reusar lo existente (`metadata_json`, `to_dict`, `_resolve_db_readonly`, `HarnessFlagsPanel`, selector runtime del Plan 36).
- **Seguridad de credenciales (Bloque C):** el password read-only NUNCA se loguea ni se inyecta en el prompt del agente. Solo el **usuario** read-only (no secreto) puede inyectarse como dato de contexto. El password sigue viviendo cifrado en `auth/db_readonly.json` y solo lo usa el código server-side.
- **TDD:** test primero en cada fase backend. Frontend: vitest NO está instalado → criterio degradado a `npm run build` (0 errores TS) + verificación manual descrita.
- **Fixes basados en evidencia (Bloques B y C):** B0 y C0 son fases de **diagnóstico con traceback/lectura real**; el fix se fija recién con la evidencia capturada. Prohibido fijar el fix a ciegas.
- **Validación por archivo:** la suite backend completa está contaminada (baseline conocido ~40F/449E incluso en HEAD por pin `pywin32==306` roto en py3.13). Correr SIEMPRE los tests **por archivo** con el python del `.venv`. NO correr la suite completa como criterio.

---

# BLOQUE B — FIX BUG 500 AL CREAR ÉPICA CON CLAUDE CODE CLI

> Se pone primero porque es el bug más urgente y el más acotado.

### B0 — Reproducir y capturar la causa raíz exacta (diagnóstico con evidencia, NO fix todavía)

**Objetivo (1 frase).** Capturar el traceback REAL que produce el 500 para fijar el fix correcto, en vez de adivinar.

**Valor.** Evita un fix a ciegas. El `request_id` del error (`f39bf031-...`) indica que Flask atrapó una excepción no controlada; necesitamos saber cuál.

**Evidencia ya recolectada (no re-explorar, está confirmada):**
- `backend/api/agents.py:544-620` — `run_brief()`: solo `except agent_runner.UnknownAgentError` (`:613`). Cualquier otra excepción de `run_agent` (`:602`) burbujea → Flask 500 con `request_id`.
- `backend/agent_runner.py:140-151` — para `runtime in {"codex_cli","claude_code_cli"}` se delega a `_start_cli_runtime(...)`. Si esa función lanza, no hay `try` que lo contenga en el path del brief.
- `run-brief` crea/reusa un "Brief Pool Ticket" con `ado_id=-1`, `stacky_project_name=None` (`agents.py:569-588`). Sospechoso #1: `_start_cli_runtime` o el claude runner resuelven output dir / client profile / sesión asumiendo un ticket "real".

**Pasos de diagnóstico (ejecutar y registrar el resultado en el PR, no inventar):**
1. Localizar el handler global de errores que arma `{"error":"Internal server error","request_id":...}`. Comando:
   ```
   cd "Stacky Agents/backend"
   grep -rn "Internal server error" . --include=*.py
   ```
   Confirmar dónde se loguea el traceback asociado a ese `request_id` (probable: `app.py` `errorhandler(500)` o un `@app.errorhandler(Exception)`). Leer ESA función y verificar que loguea `traceback.format_exc()`. Si NO lo loguea, ese es el primer arreglo (ver B1).
2. Escribir un test de reproducción que invoque `run-brief` con `runtime="claude_code_cli"` usando el `test_client()` y stubeando el CLI para que NO spawnee proceso real (patrón de `backend/tests/test_claude_code_cli_phase1.py`). El objetivo del test en B0 es **observar la excepción**, capturándola con `caplog`/`pytest.raises` a nivel de `run_agent`.
3. Registrar en el PR: el tipo de excepción y la línea exacta donde se origina dentro de `_start_cli_runtime` / `claude_code_cli_runner`. Causas candidatas a confirmar (elegir la real, no asumir):
   - (a) `start_claude_code_cli_run` exige un output dir resoluble desde el ticket y `ado_id=-1` rompe `_resolve_ticket_output_dir_ws1` (`api/executions.py`).
   - (b) la sesión claude no está logueada y el runner lanza en vez de devolver error de ejecución.
   - (c) `client_profile` requerido y ausente para el pool ticket.

**Archivo de test (diagnóstico):** `backend/tests/test_run_brief_claude_cli_repro.py` (nuevo, se reutiliza/expande en B2).

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_run_brief_claude_cli_repro.py -q
```
(PowerShell: `& ".venv\Scripts\python.exe" -m pytest tests\test_run_brief_claude_cli_repro.py -q`.)

**Criterio de aceptación (binario):** el PR documenta el tipo de excepción exacto y `archivo:línea` de origen, reproducido por un test que falla con esa excepción ANTES del fix.

**Flag:** ninguno (diagnóstico). **Trabajo del operador: ninguno.**

**Impacto por runtime:** el repro es específico de `claude_code_cli`; se debe verificar también que `codex_cli` y `github_copilot` por el mismo endpoint `run-brief` NO regresionen (B2 los cubre).

---

### B1 — Manejo de error robusto en `run-brief` (nunca 500 genérico)

**Objetivo (1 frase).** Que `run-brief` capture cualquier fallo de `run_agent` y devuelva un error HTTP accionable con mensaje, en vez de un 500 opaco.

**Valor.** Cierra KPI-B1 inmediatamente y mejora el diagnóstico para los 3 runtimes (no solo claude).

**Archivo exacto a editar:** `backend/api/agents.py`, función `run_brief()` (`:544-620`).

**Cambio (envolver la llamada a `run_agent` y mapear errores):**
```python
# Reemplazar el bloque try/except actual (agents.py:601-614) por:
user = current_user()
try:
    execution_id = agent_runner.run_agent(
        agent_type="business",
        ticket_id=pool_ticket_id,
        context_blocks=context_blocks,
        user=user,
        runtime=runtime_raw,
        vscode_agent_filename=vscode_agent_filename,
        project_name=project_name,
        use_few_shot=False,
        use_anti_patterns=False,
    )
except agent_runner.UnknownAgentError:
    abort(400, "agent_type 'business' no está registrado")
except Exception as exc:  # noqa: BLE001
    # NO dejar burbujear: el operador debe ver un mensaje accionable, no un 500 opaco.
    logger.exception(
        "run_brief: fallo al lanzar BusinessAgent runtime=%s project=%s",
        runtime_raw, project_name,
    )
    return jsonify({
        "ok": False,
        "error": "agent_launch_failed",
        "runtime": runtime_raw,
        "message": str(exc) or "No se pudo lanzar el Agente de Negocio.",
    }), 502
```
Casos borde: `runtime_raw` claude/codex que falla en preparación → 502 con `message` real (no 500). `business` no registrado → 400 (igual que hoy). Éxito → 202 (igual que hoy).

> Nota: 502 (no 500) comunica "fallo en un servicio dependiente (el runner CLI)" y es distinguible por el frontend del 404 de feature-disabled. El frontend (`EpicFromBriefModal.tsx:136-140`) ya muestra `e.message` en el estado de error, así que el mensaje accionable aparece sin tocar la UI.

**Refuerzo del handler global (si B0 detectó que no loguea traceback):** en `backend/app.py`, asegurar que el `errorhandler` que arma `{"error":"Internal server error","request_id":...}` loguee `logger.exception(...)` con el `request_id` para que cualquier 500 futuro sea diagnosticable. Cambio mínimo, aditivo, no cambia la respuesta al cliente.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_run_brief_error_handling.py` (nuevo).
Casos (stub de `agent_runner.run_agent` con monkeypatch):
1. `test_run_brief_runner_exception_returns_502_not_500`: `run_agent` lanza `RuntimeError("boom")` → status 502, `resp.json["error"]=="agent_launch_failed"`, `"boom"` en `message`. NUNCA 500.
2. `test_run_brief_unknown_agent_returns_400`: `run_agent` lanza `UnknownAgentError` → 400.
3. `test_run_brief_success_returns_202`: `run_agent` devuelve `123` → 202, `resp.json["execution_id"]==123`.
4. `test_run_brief_missing_brief_returns_400`: body sin `brief` → 400 (regresión del comportamiento existente).

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_run_brief_error_handling.py -q
```

**Criterio de aceptación (binario):** 4 passed.

**Flag:** ninguno (manejo de error siempre activo; es estrictamente más seguro). **Trabajo del operador: ninguno.**

**Impacto por runtime:** mejora los 3 (cualquier runner que falle en `run-brief` ahora da mensaje claro). Fallback: ninguno necesario; es un envoltorio defensivo.

---

### B2 — Arreglar la causa raíz confirmada en B0 (Brief Pool Ticket en path CLI)

**Objetivo (1 frase).** Que lanzar el BusinessAgent con `claude_code_cli` (y `codex_cli`) sobre el Brief Pool Ticket `ado_id=-1` prepare correctamente la sesión/output dir sin lanzar.

**Valor.** Cierra KPI-B2: el flujo brief→épica funciona end-to-end en claude_code_cli, no solo "no rompe con 500".

**Archivos exactos (elegir según lo que B0 confirme; editar SOLO el que corresponda a la causa real):**
- Si la causa es output dir: `backend/services/claude_code_cli_runner.py` y/o `backend/api/executions.py` (`_resolve_ticket_output_dir_ws1`) — hacer que un ticket con `ado_id=-1` resuelva a un dir de pool determinista (p. ej. `Agentes/outputs/brief-pool/<project>/`) en vez de fallar.
- Si la causa es sesión claude no logueada: que el runner devuelva un **error de ejecución** marcando la fila como `error` con mensaje "Claude CLI no logueado: configurá la sesión", en vez de lanzar (consistente con el manejo del Plan 37). Ese error ya queda capturado por B1 como 502 si ocurre antes de crear la fila.
- Si la causa es client_profile requerido: el BusinessAgent NO requiere client profile (`BusinessAgent.agent.md` debe tener `stacky_requires_client_profile: false`, verificar y corregir si está en true).

**Pseudocódigo (caso output dir — el más probable):**
```python
# en la resolución de output dir para runs CLI, antes de construir la ruta:
if ticket.ado_id is not None and int(ticket.ado_id) < 0:
    # Brief Pool Ticket / tickets sintéticos: dir de pool, no derivado de ado_id real.
    return outputs_root / "brief-pool" / (project_name or "default")
```
Caso borde: `project_name=None` → usar `"default"`. El dir se crea con `mkdir(parents=True, exist_ok=True)`. No se toca la resolución de tickets reales (`ado_id >= 0`).

**TDD — test PRIMERO.** Expandir `backend/tests/test_run_brief_claude_cli_repro.py`:
1. `test_run_brief_claude_cli_no_500`: con el CLI stubeado (no spawnea), `run-brief` con `runtime="claude_code_cli"` → status 202 y `execution_id` presente (ya NO lanza la excepción de B0).
2. `test_run_brief_codex_cli_no_regression`: idem con `runtime="codex_cli"` → 202.
3. `test_run_brief_copilot_no_regression`: idem con `runtime="github_copilot"` → 202.
4. `test_brief_pool_output_dir_resolves`: el resolver de output dir con un ticket `ado_id=-1` devuelve un path bajo `brief-pool/` y NO lanza (si la causa fue output dir).

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_run_brief_claude_cli_repro.py -q
```

**Criterio de aceptación (binario):** todos passed; el test de B0 que reproducía la excepción ahora pasa (ya no se lanza).

**Flag:** ninguno (es un fix de bug; el comportamiento corregido es el correcto). **Trabajo del operador: ninguno.**

**Impacto por runtime:**
- Claude Code CLI: deja de dar 500; ejecuta o da error accionable.
- Codex CLI: mismo path corregido (también usa `_start_cli_runtime`).
- GitHub Copilot: no usa `_start_cli_runtime`; se cubre con test de no-regresión.
- Fallback: si la sesión del runtime CLI no está lista, error de ejecución accionable (Plan 37), nunca 500.

**Verificación manual (KPI-B2):** abrir el modal "Épica desde brief", elegir Claude Code CLI, pegar un brief, generar → la ejecución corre y produce el Epic HTML; aprobar → la épica se crea. Sin 500.

---

# BLOQUE C — FIX: EL AGENTE NO USA EL USUARIO READ-ONLY DEL PERFIL AL ACCEDER A LA DB

### C0 — Diagnóstico con evidencia: por qué se ignora el usuario read-only

**Objetivo (1 frase).** Confirmar con lectura del perfil real de RSPACIFICO por qué el agente usa Windows-auth en vez del usuario read-only, antes de fijar el fix.

**Valor.** Evita "arreglar" el lugar equivocado. Hay 3 puntos posibles de falla; hay que saber cuál aplica.

**Evidencia ya recolectada (confirmada, no re-explorar):**
- `backend/services/db_query.py:14-27` — el módulo es un **stub**: valida y audita pero NO ejecuta la query (`would_execute=True`, `:277-314`). O sea, si el agente realmente consulta la BD, NO lo está haciendo por este endpoint.
- `backend/services/db_query.py:194-220` — `_resolve_db_readonly(project)`: el `user` se resuelve como `payload.get("user")` (de `auth/db_readonly.json`) **o** `db.get("readonly_user_hint")`. Si ambos están vacíos, `user==""`.
- `backend/services/client_profile_default_templates.py:52-53` — default: `readonly_user_hint=""`, `connection_kind="windows_sqlcmd"`. La auth integrada de Windows es el default.
- `backend/Stacky/agents/Developer.agent.md:104` — el agente tiene instrucción de que "el password de BD NO está en el client-profile" y de emitir SQL (`dml_policy=prohibited_runtime_must_emit_sql`).

**Pasos de diagnóstico (ejecutar y registrar; no inventar):**
1. Leer el perfil real del proyecto RSPACIFICO: localizar su `config.json` y `auth/db_readonly.json`. Comando (ajustar nombre de proyecto si difiere):
   ```
   cd "Stacky Agents/backend"
   grep -rn "connection_kind\|readonly_user_hint\|readonly_auth_ref" ../../DeployStackyAgents/data 2>/dev/null
   ```
   (Si la DB viva está en `DeployStackyAgents/data` — ver memoria de rutas del runtime.) Registrar: ¿`auth/db_readonly.json` existe para RSPACIFICO? ¿tiene `user` poblado? ¿`connection_kind` es `windows_sqlcmd`?
2. Determinar CÓMO accede el agente a la BD en RSPACIFICO. Dos hipótesis:
   - (H1) El agente arma `sqlcmd -E` (Windows-auth) por su cuenta porque `connection_kind="windows_sqlcmd"` y el `.agent.md`/contexto no le pasan el usuario read-only.
   - (H2) El agente usa el endpoint `db_query` (stub) — descartada para "acceso real", porque el stub no ejecuta.
   Confirmar con `grep` de cómo se inyecta `database` al contexto: `backend/services/context_enrichment.py:478` (`build_client_profile_block`) y qué campos de `database` llegan al prompt.
3. Registrar en el PR cuál hipótesis es la real. Lo más probable (por la evidencia) es **H1**: el agente recibe `connection_kind="windows_sqlcmd"` y ningún usuario read-only explícito, así que usa la identidad de la máquina.

**Archivo de test (diagnóstico):** `backend/tests/test_db_readonly_resolution.py` (nuevo, se expande en C1).

**Criterio de aceptación (binario):** el PR documenta cuál de H1/H2 es la causa, con `archivo:línea` y el contenido (sin secretos) del perfil RSPACIFICO relevante.

**Flag:** ninguno. **Trabajo del operador: ninguno** (salvo, fuera de plan, tener la credencial read-only cargada — ya documentado en `POST /api/projects/<name>/db-readonly-auth`).

---

### C1 — Hacer del usuario read-only la fuente de verdad resuelta (backend)

**Objetivo (1 frase).** Que `_resolve_db_readonly` priorice y exponga SIEMPRE el usuario read-only configurado, y que exista un helper único que diga "qué usuario/modo de conexión debe usar el agente".

**Valor.** Cierra KPI-C1. Un solo punto de verdad para el usuario de BD que el agente debe usar.

**Archivo exacto a editar:** `backend/services/db_query.py`, función `_resolve_db_readonly` (`:194-220`).

**Cambio 1 — priorizar el usuario explícito y nunca caer silenciosamente a vacío:**
```python
# dentro de _resolve_db_readonly, al armar el dict de retorno:
resolved_user = (
    payload.get("user")              # 1) usuario explícito del auth file (verdad)
    or db.get("readonly_user_hint")  # 2) hint del perfil
    or ""
)
return {
    "server":   payload.get("server") or db.get("server") or "",
    "database": payload.get("database") or "",
    "user":     resolved_user,
    "password": password_secret.value,
    "auth_file": auth_ref,
    "dialect":  db.get("type") or "",
    # NUEVO: modo de conexión efectivo. Si hay usuario read-only resuelto,
    # el modo DEBE ser autenticación por usuario, NO Windows-integrated.
    "connection_mode": "sql_login" if resolved_user else (db.get("connection_kind") or ""),
}
```
Caso borde: sin auth file → devuelve `{}` (igual que hoy; el agente sabe que no hay read-only y cae al comportamiento previo, sin degradar). Con auth file pero sin `user` ni `readonly_user_hint` → `user=""` y `connection_mode` cae a `connection_kind` (Windows-auth heredado); pero esto se reporta como warning (ver C2).

**Cambio 2 — helper público nuevo** en `db_query.py`:
```python
def get_db_access_directive(project_name: str) -> dict:
    """Fuente de verdad para 'cómo debe conectarse el agente a la BD'.
    Devuelve { has_readonly: bool, user: str, server: str, dialect: str,
               connection_mode: str, must_avoid_windows_auth: bool }.
    NO devuelve el password (no es para el agente)."""
    auth = _resolve_db_readonly(project_name)
    if not auth:
        return {"has_readonly": False, "user": "", "server": "", "dialect": "",
                "connection_mode": "", "must_avoid_windows_auth": False}
    return {
        "has_readonly": True,
        "user": auth.get("user") or "",
        "server": auth.get("server") or "",
        "dialect": auth.get("dialect") or "",
        "connection_mode": auth.get("connection_mode") or "sql_login",
        "must_avoid_windows_auth": bool(auth.get("user")),
    }
```
Este helper NO expone el password: solo el usuario (no secreto) y el modo. Es lo único que puede inyectarse al contexto del agente.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_db_readonly_resolution.py` (nuevo).
Casos (usar `tmp_path` + monkeypatch de `PROJECTS_DIR` y de `read_secret_from_file`; patrón de `test_db_query_audit.py`):
1. `test_resolve_prefers_payload_user`: auth file con `user="svc_ro"` → `_resolve_db_readonly(...)["user"]=="svc_ro"` y `connection_mode=="sql_login"`.
2. `test_resolve_falls_back_to_hint`: auth file sin `user`, perfil con `readonly_user_hint="hint_ro"` → `user=="hint_ro"`, `connection_mode=="sql_login"`.
3. `test_directive_has_readonly_true_and_avoid_windows`: `get_db_access_directive` con auth file y user → `has_readonly True`, `must_avoid_windows_auth True`, y `"password"` NO está en el dict devuelto.
4. `test_directive_no_auth_file_is_safe`: sin auth file → `has_readonly False`, sin lanzar.
5. `test_directive_never_returns_password`: el dict de `get_db_access_directive` no contiene la clave `password` en ningún caso.

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_db_readonly_resolution.py -q
```

**Criterio de aceptación (binario):** 5 passed.

**Flag:** ninguno (es la resolución correcta; no cambia comportamiento cuando no hay auth file). **Trabajo del operador: ninguno.**

**Impacto por runtime:** ninguno directo (es lógica de resolución compartida por los 3).

---

### C2 — Inyectar la directiva de DB read-only al contexto del agente (sin password)

**Objetivo (1 frase).** Que, cuando hay credencial read-only configurada, el bloque de contexto del agente diga explícitamente "usá el usuario `<X>` (sql_login), NO autenticación integrada de Windows", reusando el seam de armado de contexto.

**Valor.** Cierra KPI-C2: el agente recibe el usuario read-only como dato y se le desaconseja Windows-auth. Es la pieza que faltaba para que el agente "lea correctamente el perfil del cliente".

**Archivo exacto a editar:** `backend/services/context_enrichment.py`, función `build_client_profile_block` (`:478`).

**Cambio (aditivo, gated por flag):** al construir el bloque del client-profile, si el flag está ON y `get_db_access_directive(project_name)["has_readonly"]` es True, anexar una sección clara al bloque:
```python
from services.db_query import get_db_access_directive
# ... dentro de build_client_profile_block, tras armar el bloque base:
if config.STACKY_DB_READONLY_DIRECTIVE_ENABLED:
    directive = get_db_access_directive(project_name)
    if directive["has_readonly"]:
        block_text += (
            "\n\n### Acceso a base de datos (OBLIGATORIO)\n"
            f"- Conectarse SIEMPRE con el usuario de SOLO LECTURA del perfil: "
            f"`{directive['user']}` (modo {directive['connection_mode']}).\n"
            f"- Servidor: `{directive['server']}` | Motor: `{directive['dialect']}`.\n"
            "- PROHIBIDO usar autenticación integrada de Windows (`-E` / Trusted_Connection) "
            "cuando hay un usuario read-only configurado.\n"
            "- El password NO se incluye aquí: se resuelve server-side al ejecutar la consulta.\n"
        )
```
Casos borde: sin read-only configurado → no se anexa nada (comportamiento idéntico a hoy). Con read-only → se anexa el usuario (no secreto). NUNCA se anexa el password. Best-effort: si `get_db_access_directive` lanza, capturar y omitir la sección con warning (igual que el resto de `build_client_profile_block`).

> Importante: NO eliminar la instrucción existente del `.agent.md` sobre `dml_policy`; esta directiva la complementa diciendo QUÉ usuario usar cuando el agente sí necesita conectar. Si la política del proyecto es "Stacky emite SQL y el operador ejecuta", el usuario read-only igual es el correcto para cuando el agente valida/conecta.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_context_db_directive.py` (nuevo).
Casos (monkeypatch de `get_db_access_directive`):
1. `test_directive_injected_when_readonly_present`: directiva con `user="svc_ro"`, flag ON → el bloque contiene `"svc_ro"` y `"SOLO LECTURA"` y `"PROHIBIDO usar autenticación integrada"`.
2. `test_directive_never_contains_password`: aunque el auth file tenga password, el bloque NO contiene el password (verificar con un valor centinela).
3. `test_no_directive_when_no_readonly`: `has_readonly False` → el bloque NO contiene la sección de acceso a BD.
4. `test_flag_off_is_byte_identical`: flag OFF → el bloque es idéntico al de hoy (sin la sección).

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_context_db_directive.py -q
```

**Criterio de aceptación (binario):** 4 passed.

**Flag:** `STACKY_DB_READONLY_DIRECTIVE_ENABLED` (env var en `backend/config.py`). **Default seguro: `"true"`** (es una mejora de seguridad: empujar al agente a usar el usuario read-only en vez de la identidad de la máquina; cuando NO hay read-only configurado el flag es inerte). Registrar en `.env.example` y en `FLAG_REGISTRY` (`backend/services/harness_flags.py`) con `group="database"`, `type=bool`, label y description (Plan 33 → aparece en `HarnessFlagsPanel` sin tocar frontend).
```
# Plan 39 — inyecta al contexto del agente la directiva de usar el usuario read-only
# del perfil (NO Windows-auth) cuando hay auth/db_readonly.json configurado.
STACKY_DB_READONLY_DIRECTIVE_ENABLED=true
```

**Impacto por runtime:** el bloque de contexto se inyecta igual en los 3 runtimes (Codex/Claude/Copilot) porque `build_client_profile_block` es el seam único. Fallback: si la directiva no se puede armar, se omite con warning; el agente cae al comportamiento previo (sin degradar).

**Trabajo del operador: ninguno** (automático cuando ya cargó la credencial read-only; si no la cargó, no cambia nada).

---

# BLOQUE A — HISTORIAL DE EJECUCIONES COMPLETO

### A0 — Asegurar que la duración se persiste/expone por ejecución

**Objetivo (1 frase).** Garantizar que cada `AgentExecution` exponga `duration_ms` (derivado de `started_at`/`finished_at`) en su `to_dict()`.

**Valor.** El "tiempo que tardó" es el dato #1 pedido; debe estar disponible sin recalcular en el frontend.

**Archivo exacto a editar:** `backend/models.py`, método `AgentExecution.to_dict()` (la clase `AgentExecution` y su `to_dict` están en `models.py`; confirmar la línea con grep `class AgentExecution` y `def to_dict`).

**Cambio (aditivo):** en `to_dict()`, agregar:
```python
# duración derivada; None si aún corre o falta timestamp.
_dur = None
if self.started_at and getattr(self, "finished_at", None):
    _dur = int((self.finished_at - self.started_at).total_seconds() * 1000)
result["duration_ms"] = _dur
```
Usar el nombre real del campo de fin (`finished_at` / `completed_at` / `ended_at` — confirmar con grep en `models.py`). Si no existe un campo de fin persistido, derivar de la última escritura conocida; si tampoco, dejar `duration_ms=None` (nunca lanzar). NO renombrar campos existentes.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_execution_duration.py` (nuevo).
Casos:
1. `test_duration_computed_when_finished`: una ejecución con `started_at` y fin a +5s → `to_dict()["duration_ms"]` ≈ 5000.
2. `test_duration_none_when_running`: sin fin → `duration_ms is None`.
3. `test_existing_fields_unchanged`: `to_dict()` sigue conteniendo `status`, `agent_type`, `metadata`.

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_execution_duration.py -q
```

**Criterio de aceptación (binario):** 3 passed.

**Flag:** ninguno (campo aditivo de solo lectura). **Trabajo del operador: ninguno.**

**Impacto por runtime:** ninguno (los 3 escriben `started_at`/fin igual).

---

### A1 — Endpoint de historial enriquecido y filtrable

**Objetivo (1 frase).** `GET /api/executions/history` que devuelve una lista de runs con TODOS los campos para la tabla de historial, con filtros y paginación.

**Valor.** Un solo endpoint que el frontend consume para la vista de historial. Cierra KPI-A1.

**Archivo exacto a editar:** `backend/api/executions.py` (mismo blueprint `bp`, `url_prefix="/executions"`).

**Símbolo exacto:** nueva ruta `@bp.get("/history")` → función `executions_history()`.

**Contrato de salida (cada item):**
```
{
  "id": int, "ticket_id": int, "ticket_title": str | null,
  "agent_type": str, "agent_name": str | null,
  "runtime": str | null, "model": str | null,
  "status": str,
  "started_at": iso str | null, "finished_at": iso str | null, "duration_ms": int | null,
  "cost_usd": float | null, "tokens_in": int | null, "tokens_out": int | null,
  "prompt_sha": str | null, "prompt_len": int | null,
  "has_prompt_text": bool,                 # true si metadata trae prompt_text (Plan 38)
  "produced_files_count": int,
  "error_message": str | null
}
```
Los valores se extraen de columnas existentes + `metadata` (Plan 38 dejó `prompt_sha`, `agent_type`, `produced_files`, `runtime`; el costo/modelo ya existen — confirmar las keys reales con grep `cost\|model\|tokens` en `models.py` y en la metadata que escriben los runners). Para campos ausentes en ejecuciones viejas → `null` / `0` / `false` (nunca lanzar).

**Query params (todos opcionales):** `project`, `agent_type`, `runtime`, `status` (csv), `days`, `limit` (default 100, máx 500), `offset` (paginación). Reusar la lógica de filtro de `list_executions` (`executions.py:26-81`).

**Pseudocódigo:**
```python
@bp.get("/history")
def executions_history():
    # reusar parsing de project/agent_type/status/days/limit de list_executions
    limit = min(request.args.get("limit", default=100, type=int), 500)
    offset = request.args.get("offset", default=0, type=int)
    with session_scope() as session:
        q = session.query(AgentExecution)  # + mismos filtros que list_executions
        # ... aplicar filtros project/agent_type/runtime/status/days ...
        rows = (q.order_by(AgentExecution.started_at.desc())
                  .offset(offset).limit(limit).all())
        items = [_history_item(r, session) for r in rows]
    return jsonify({"items": items, "limit": limit, "offset": offset, "count": len(items)})

def _history_item(row, session) -> dict:
    md = row.metadata_dict or {}
    d = row.to_dict(include_output=False)  # ya trae status, agent_type, metadata, duration_ms (A0)
    ticket = session.get(Ticket, row.ticket_id) if row.ticket_id else None
    return {
        "id": row.id, "ticket_id": row.ticket_id,
        "ticket_title": getattr(ticket, "title", None),
        "agent_type": row.agent_type, "agent_name": md.get("agent_name"),
        "runtime": md.get("runtime"), "model": md.get("model") or getattr(row, "model", None),
        "status": row.status,
        "started_at": d.get("started_at"), "finished_at": d.get("finished_at"),
        "duration_ms": d.get("duration_ms"),
        "cost_usd": md.get("cost_usd") or getattr(row, "cost_usd", None),
        "tokens_in": md.get("tokens_in"), "tokens_out": md.get("tokens_out"),
        "prompt_sha": md.get("prompt_sha"), "prompt_len": md.get("prompt_len"),
        "has_prompt_text": bool(md.get("prompt_text")),
        "produced_files_count": len(md.get("produced_files") or []),
        "error_message": row.error_message,
    }
```
> Confirmar con grep las keys reales de costo/modelo/tokens (`grep -n "cost\|model\|tokens" backend/models.py backend/services/*runner*.py`). Usar las que existan; las que no, quedan `null`. NO inventar columnas.

**TDD — test PRIMERO.** Archivo: `backend/tests/test_executions_history.py` (nuevo).
Casos (sembrar 2-3 `AgentExecution` en DB de test; patrón de otros tests de `executions`):
1. `test_history_returns_items_with_all_keys`: GET `/executions/history` → 200, cada item tiene las claves del contrato (incluida `duration_ms`, `cost_usd`, `model`, `runtime`, `prompt_sha`).
2. `test_history_filters_by_agent_type`: `?agent_type=developer` → solo runs de developer.
3. `test_history_filters_by_runtime`: `?runtime=claude_code_cli` → solo esos.
4. `test_history_pagination`: `?limit=1&offset=1` → 1 item, el segundo más reciente.
5. `test_history_old_execution_no_crash`: una ejecución sin claves de Plan 38 en metadata → item con `null`/`0`/`false`, sin error.

**Comando exacto:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_executions_history.py -q
```

**Criterio de aceptación (binario):** 5 passed.

**Flag:** `STACKY_EXECUTION_HISTORY_ENABLED` (env, `config.py`), default `"true"` (lectura inerte). Si OFF → 404 `feature_disabled`. Registrar en `FLAG_REGISTRY` (group `observability`) + `.env.example`.

**Impacto por runtime:** muestra los 3 runtimes de forma uniforme (lee metadata común del Plan 38/36). **Trabajo del operador: ninguno.**

---

### A2 — Página de historial en el frontend

**Objetivo (1 frase).** Una página/tab "Historial" con una tabla filtrable de todos los runs y, al clickear una fila, el drawer de detalle existente (Plan 38 C2).

**Valor.** Cierra KPI-A2. El operador ve todo en un lugar y profundiza en el detalle reusando el drawer.

**Archivos exactos:**
- `frontend/src/api/endpoints.ts` (editar) — agregar `Executions.history(params)`.
- `frontend/src/pages/ExecutionHistoryPage.tsx` (nuevo) — la tabla.
- `frontend/src/pages/ExecutionHistoryPage.module.css` (nuevo).
- Registrar la ruta/tab donde se registran las demás páginas (buscar dónde se monta `DiagnosticsPage` o el router de páginas; replicar ese patrón). NO inventar un router nuevo.

**Cambio en `endpoints.ts`:**
```ts
// dentro del objeto Executions existente
history: (params?: { project?: string; agent_type?: string; runtime?: string;
  status?: string; days?: number; limit?: number; offset?: number }) =>
  api.get<{ items: ExecutionHistoryItem[]; limit: number; offset: number; count: number }>(
    "/api/executions/history", { params }),
```
Definir el tipo `ExecutionHistoryItem` con las claves del contrato A1 (todas opcionales/nullable salvo `id`, `status`, `agent_type`).

**Tabla (columnas):** Inicio | Agente | Runtime | Modelo | Estado | Duración (formateada: `Xs`/`Xm Ys`) | Costo (USD, `—` si null) | Prompt (`sha …` o botón "ver" si `has_prompt_text`) | Archivos (count) | Ticket.
Filtros arriba: agente, runtime, estado, días, proyecto. Paginación con `limit`/`offset`.
Click en fila → abrir `ExecutionDetailDrawer` (componente existente, Plan 38 C2) con ese `execution_id`. NO duplicar el detalle.

Caso borde: lista vacía → "Sin ejecuciones". Campo null → `—`. Nunca crashea con ejecuciones viejas.

**TDD — vitest no instalado → criterio degradado.**
- Obligatorio: `cd "Stacky Agents/frontend" && npm run build` → 0 errores TS.
- Verificación manual:
  1. Abrir "Historial" → tabla con runs recientes, columnas de tiempo/modelo/costo/estado pobladas.
  2. Filtrar por runtime `claude_code_cli` → solo esos.
  3. Click en una fila → drawer de detalle con prompt/archivos (Plan 38).
  4. Una ejecución vieja sin datos nuevos → muestra `—`, sin error.

**Criterio de aceptación (binario):** `npm run build` 0 errores TS + las 4 verificaciones manuales OK.

**Flag:** reusa `STACKY_EXECUTION_HISTORY_ENABLED` (si el endpoint da 404, la página muestra "Historial deshabilitado"). **Trabajo del operador: ninguno.**

**Impacto por runtime:** vista uniforme de los 3.

---

## 4. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| B1 oculta el error real al devolver 502 genérico. | B1 incluye el `str(exc)` en `message` y `logger.exception` con traceback; B0 ya documentó la causa. No se pierde diagnóstico. |
| B2 arregla el síntoma pero no la causa (pool ticket). | B0 obliga a capturar el traceback real ANTES; B2 edita SOLO el archivo de la causa confirmada. Tests de no-regresión para codex/copilot. |
| C2 filtra el password al prompt. | `get_db_access_directive` (C1) NO devuelve password; test `test_directive_never_returns_password` + `test_directive_never_contains_password`. El password sigue server-side. |
| C2 cambia el comportamiento de proyectos sin read-only. | La sección solo se anexa si `has_readonly True`; sin auth file el flag es inerte (test `test_no_directive_when_no_readonly`). |
| C2 contradice el `.agent.md` (dml_policy). | C2 complementa, no reemplaza: dice QUÉ usuario usar; el plan prohíbe tocar la instrucción dml_policy existente. |
| A1 asume columnas de costo/modelo que no existen. | El plan obliga a grep de las keys reales; las ausentes quedan `null`. KPI-A1 exige que las CLAVES existan, no que tengan valor. |
| A0 asume un campo `finished_at` que no existe. | El plan obliga a confirmar el nombre real con grep; si no hay, `duration_ms=None`, nunca lanza. |
| Suite contaminada hace fallar la validación. | Correr SIEMPRE por archivo con el python del `.venv`; nunca la suite completa (baseline conocido). |
| Frontend sin vitest deja gaps. | Criterio degradado a `npm run build` + verificación manual; instalación opcional documentada. |

## 5. Fuera de scope

- Ejecutar de verdad las queries contra la BD (`db_query.py` sigue siendo stub para la EJECUCIÓN; este plan solo arregla QUÉ usuario/modo se resuelve e inyecta). Enchufar el driver real es otro plan.
- Cambiar `dml_policy` o la política "Stacky emite SQL, operador ejecuta".
- Nuevas columnas en la DB (todo va en `metadata_json`/columnas existentes; sin migración de esquema).
- Cálculo retroactivo de costo/duración para ejecuciones viejas (solo se expone lo persistido; viejas → `null`).
- RBAC/multiusuario; export del historial a CSV/Excel (puede ser plan futuro).
- Reescribir el runner Copilot, el router de modelos o el selector de runtime (Plan 36/37 ya cerrados).
- Editor visual de épicas (Plan 38).

## 6. Glosario

- **`AgentExecution` / run / ejecución:** fila que representa una corrida de un agente sobre un ticket (`backend/models.py`). Su `metadata_json` (expuesto como `metadata` por `to_dict()`) guarda runtime, prompt_sha, agent_type, produced_files, costo, etc.
- **runtime:** Codex CLI / Claude Code CLI / GitHub Copilot. Se elige con el selector del Plan 36; se persiste en `metadata["runtime"]`.
- **`run-brief`:** endpoint `POST /api/agents/run-brief` (Plan 38) que lanza el BusinessAgent sobre un "Brief Pool Ticket" sintético (`ado_id=-1`) para generar una Épica desde un brief.
- **Brief Pool Ticket:** ticket local sintético con `ado_id=-1` por proyecto, usado para anclar ejecuciones de brief sin un work item real.
- **`auth/db_readonly.json`:** archivo cifrado (DPAPI) por proyecto con `server`/`database`/`user`/`password` del usuario de SOLO LECTURA de la BD del cliente. El password nunca se inyecta al agente.
- **`connection_kind` / `connection_mode`:** cómo se conecta a la BD. `windows_sqlcmd` = autenticación integrada de Windows (usa la identidad de la máquina). `sql_login` = usuario/contraseña explícitos (lo correcto cuando hay read-only).
- **`build_client_profile_block`:** seam único (`context_enrichment.py:478`) que arma el bloque de client-profile inyectado al prompt de los 3 runtimes.
- **stub `db_query.py`:** valida y audita queries SELECT pero NO las ejecuta hoy (`would_execute=True`).
- **human-in-the-loop:** el operador aprueba; nunca se reemplaza su decisión. Este plan no agrega autonomía.

## 7. Orden de implementación y DoD

**Orden de implementación (numerado; bloques independientes, dentro de cada uno respetar el orden):**
1. **B0** — reproducir y capturar la causa del 500 (diagnóstico).
2. **B1** — manejo de error robusto en `run-brief` (nunca 500) + tests.
3. **B2** — fix de la causa raíz (pool ticket / output dir / sesión) + tests.
4. **C0** — diagnóstico del usuario read-only ignorado (evidencia del perfil RSPACIFICO).
5. **C1** — `_resolve_db_readonly` prioriza usuario read-only + helper `get_db_access_directive` + tests.
6. **C2** — inyectar la directiva de DB read-only al contexto del agente + tests.
7. **A0** — `duration_ms` en `to_dict()` + tests.
8. **A1** — endpoint `GET /api/executions/history` + tests.
9. **A2** — página de historial (frontend).

**Definición de Hecho (DoD) global (todo binario):**
- [ ] B0: el PR documenta tipo de excepción + `archivo:línea` de origen, con test que la reproduce.
- [ ] B1: `tests/test_run_brief_error_handling.py` → 4 passed (502, 400, 202, 400-missing).
- [ ] B2: `tests/test_run_brief_claude_cli_repro.py` → todos passed; ya no 500.
- [ ] C0: el PR documenta H1/H2 con evidencia del perfil RSPACIFICO (sin secretos).
- [ ] C1: `tests/test_db_readonly_resolution.py` → 5 passed; el dict del helper nunca trae `password`.
- [ ] C2: `tests/test_context_db_directive.py` → 4 passed; bloque trae el usuario read-only y nunca el password; flag OFF byte-idéntico.
- [ ] A0: `tests/test_execution_duration.py` → 3 passed.
- [ ] A1: `tests/test_executions_history.py` → 5 passed.
- [ ] A2: `npm run build` 0 errores TS + 4 verificaciones manuales (incl. ejecución vieja sin crash).
- [ ] KPI-B1: crear épica con claude_code_cli no devuelve 500 genérico (verificación manual).
- [ ] KPI-B2: flujo brief→épica con claude_code_cli completo end-to-end (verificación manual).
- [ ] KPI-C1/C2: con read-only configurado, el contexto del agente trae el usuario read-only y prohíbe Windows-auth (test + verificación manual).
- [ ] KPI-A1: `/api/executions/history` trae todas las claves del contrato para una ejecución nueva de cada runtime.
- [ ] `.env.example` documenta `STACKY_DB_READONLY_DIRECTIVE_ENABLED` y `STACKY_EXECUTION_HISTORY_ENABLED`.
- [ ] Ambos flags nuevos registrados en `FLAG_REGISTRY` (`services/harness_flags.py`) con group/type/label/description → aparecen en `HarnessFlagsPanel` (Plan 33) sin tocar frontend.
- [ ] Validación SIEMPRE por archivo con el python del `.venv`; NO correr la suite completa.

**Comando de validación global (backend, por archivo):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_run_brief_error_handling.py tests/test_run_brief_claude_cli_repro.py tests/test_db_readonly_resolution.py tests/test_context_db_directive.py tests/test_execution_duration.py tests/test_executions_history.py -q
```
**Comando de validación global (frontend):**
```
cd "Stacky Agents/frontend"
npm run build
```
