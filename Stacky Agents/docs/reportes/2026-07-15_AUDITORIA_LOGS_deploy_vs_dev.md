# Auditoría de Logs — Deploy vs Dev

- **Fecha:** 2026-07-15
- **Autor:** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8)
- **Alcance:** Revisión de logs de Stacky Agents en dos escenarios: (1) último DEPLOY publicado (v1.0.76) y (2) ejecución NORMAL en dev/local desde el repo.
- **Naturaleza:** Solo lectura. No se modificó código ni configuración. Único artefacto nuevo: este reporte.
- **Destino:** Este documento está pensado para que otro agente lo consuma con `proponer-plan-stacky`. Cada hallazgo trae severidad, evidencia citada (archivo:línea/fragmento), causa raíz con marca de confianza y una idea de mejora candidata a plan.

**Convención de confianza:** `[V]` verificado contra código/evidencia · `[INF]` inferido · `[NV]` no verificable con lo disponible.

---

## 1. Resumen ejecutivo (lo más grave primero)

- **DEPLOY — Runs de Claude Code CLI mueren en producción por workspace no confiado.** 8 ERROR + 15 WARNING: `claude code cli exited with code 1: ... this workspace has not been trusted`. El primer run (`exec=1`) sale con código 1 y el flujo de ejecución queda inutilizable. Es el bloqueo #1 de la instancia desplegada. Severidad **Crítica**.
- **DEPLOY — Runs se cuelgan y son terminados a los ~600s por el stall watchdog** (7 runs: `exec=2,3,4,6,7,8,17`), y **2 tickets (120, 121) colgados 120 min** hasta que el reaper los recupera. El operador ve trabajo que nunca termina. Severidad **Alta**.
- **DEV — Bug real de import:** `services/ado_edit_learning.py:259` hace `from models import Execution`, pero `models.py` NO exporta `Execution` (la clase es `AgentExecution`, línea 207). `sweep_recent_runs` falla **318 veces**. Severidad **Alta**. `[V]`
- **DEV/DEPLOY — Ruido masivo de 404:** `GET /api/v1/pipeline/status` devuelve 404 de forma constante: **12.094 veces en DEV** y **10.687 en DEPLOY**. La ruta no existe en el backend ni en el frontend/extension del repo; algún cliente la pollea cada pocos segundos. Ahoga los logs y esconde 404 reales. Severidad **Alta (por volumen/observabilidad)**.
- **DEV — El log operativo está contaminado por pytest:** 91 de 102 tracebacks (89%) provienen de tests (rutas `pytest-of-juanluca`, mensajes sembrados como `DB exploded`, `boom auth error`). El archivo de log de dev es poco confiable para diagnóstico real. Severidad **Media (observabilidad)**. `[V]`
- **Higiene de logs:** códigos de color ANSI (`[33m`) escritos al archivo (**6.590 en un solo día de DEPLOY**) y warnings de preflight repetidos por ciclo sin dedup (outputs_dir 4.761×, PAT ADO expirado 975×). Los archivos de log crecen y se vuelven ilegibles. Severidad **Media**.

---

## 2. Fuentes de logs analizadas (cobertura y gaps)

### DEPLOY (producción, v1.0.76 — commit `7df192a8`, generado 2026-07-13 00:34)
| Fuente | Ruta | Cobertura |
|---|---|---|
| Log runtime vivo | `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-07-13.log` (1,99 MB) | 2026-07-13 12:38 → 23:59 |
| Log runtime vivo | `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-07-14.log` (2,20 MB) | 2026-07-14 00:00 → 18:20 |
| Metadata release | `DeployStackyAgents/DEPLOY_INFO.json`, `release-manifest.json`, `VERSION.txt` | v1.0.76, `stacky_agents_count=7`, `config_exported=false` |
| Backups históricos | `DeployStackyAgents/backups/DeployStackyAgents-1.0.*/data/logs/` | No analizados en detalle (versiones viejas) |

- **Cobertura DEPLOY:** buena. Dos días de operación real (2026-07-13/14) con ejecuciones de agentes contra el proyecto `RSPACIFICO`. Log limpio de tests (refleja producción).
- **Gap DEPLOY:** no hay logs posteriores al 2026-07-14 18:20 (la instancia dejó de correr o dejó de loguear). No hay separación de stdout/stderr del `.exe` (todo va al log werkzeug/app).

### DEV (repo local, backend FastAPI/Flask)
| Fuente | Ruta | Cobertura |
|---|---|---|
| Logs runtime dev | `Stacky Agents/backend/data/logs/stacky-2026-07-01.log` … `stacky-2026-07-15.log` (15 archivos) | 2026-07-01 → 2026-07-15 13:38 |
| Install logs | `Stacky Agents/data/install_logs/install-dependencies-*.log` (60+ archivos) | 2026-06-04 → 2026-06-20 (histórico de instalación) |
| Telemetría kaizen | `kaizen/sessions/*/forensic.jsonl` | Subsistema kaizen, fuera del runtime del agente principal |

- **Cobertura DEV:** amplia (15 días), pero **mezclada con ruido de pytest** (ver Hallazgo V7). El archivo de dev sirve tanto al server local como a las corridas de tests → hay que filtrar `pytest-of-juanluca` / mensajes sembrados para diagnosticar lo real.
- **Gap DEV:** no hay telemetría estructurada del runtime del agente en `.jsonl` (los `forensic.jsonl` son del subsistema kaizen, no del pipeline de tickets). No hay logs separados de frontend (Vite/vitest) persistidos.

### Fuentes que NO se encontraron (declarado explícitamente, sin inventar)
- **Logs de frontend (dev server Vite / consola del navegador):** no se persisten en disco. Todo diagnóstico de UI depende de reproducción manual.
- **Outputs de ejecuciones en `C:\desarrollo\...\RSPACIFICO\Agentes\outputs`:** la carpeta vive en la máquina del operador, fuera del repo; en el checkout auditado el runtime la reporta como **inexistente** (ver V2). No hay artifacts de runs para inspeccionar directamente desde el repo.
- **stderr crudo del backend empaquetado (`stacky-backend.exe`):** no hay archivo separado; si el `.exe` crashea antes de inicializar el logger, no queda rastro en `data/logs/`.

---

## 3. Hallazgos DEPLOY (producción v1.0.76)

### D1 — [CRÍTICO] Runs de Claude Code CLI mueren: workspace no confiado
- **Evidencia:** `DeployStackyAgents/data/logs/stacky-2026-07-13.log:599`
  `2026-07-13 12:49:50 ERROR [stacky_agents.claude_code_cli] [exec=1] claude code cli exited with code 1: Ignoring 23 permissions.allow entries from .claude/settings.local.json: this workspace has not been trusted. Run Claude Code interactively here once and accept the trust dialog, or set projects["C:/desarrollo/GIT/RS/RSPACIFICO"].hasTrustDialogAccepted: true`
  8 ocurrencias ERROR + 15 WARNING equivalentes.
- **Causa raíz [V]:** el workspace `C:/desarrollo/GIT/RS/RSPACIFICO` no tiene `hasTrustDialogAccepted: true` en `~/.claude.json`. Claude Code CLI ignora los permisos y sale con código 1. Stacky lanza el run pero no hace preflight de "trust" ni lo auto-configura.
- **Mejora candidata a plan:** preflight de confianza de workspace antes de lanzar `claude_code_cli` — detectar el estado de `hasTrustDialogAccepted`, y (a) setearlo automáticamente para el `workspace_root` del proyecto activo, o (b) fallar temprano con un mensaje accionable en el run record (no código 1 mudo). Severidad Crítica, esfuerzo Medio.

### D2 — [ALTO] Runs colgados terminados por stall watchdog a ~600s
- **Evidencia:** `stacky-2026-07-13.log:1645,2027,2479,5522,6057,6384` y `stacky-2026-07-14.log:10027`
  `WARNING [stacky_agents.claude_code_cli] [exec=2] R1.1 stall watchdog: 605s sin eventos del stream — terminando` (7 runs: exec 2,3,4,6,7,8,17).
- **Causa raíz [INF]:** el stream del CLI no emite eventos por >600s y el watchdog lo mata. Muy probablemente **consecuencia de D1** (el CLI arranca degradado/sin permisos y no produce salida) o stalls genuinos del stream. El watchdog funciona (evita zombies), pero el run se pierde sin diagnóstico de la causa del stall.
- **Mejora candidata a plan:** enriquecer el evento de stall con la última actividad conocida (último tool_use/heartbeat) y correlacionarlo con el estado de trust/permeabilidad del CLI; exponer en la UI "run terminado por inactividad (600s) — última señal: X". Severidad Alta, esfuerzo Medio.

### D3 — [ALTO] Tickets colgados 120 min recuperados por el reaper
- **Evidencia:** `stacky-2026-07-13.log:13737-13739`
  `WARNING [stacky.ticket_status] reaper[reaper]: exec_id=12 ticket_id=121 timed_out after 120 min` + `exec_id=13 ticket_id=120` + `INFO stale-recovery reaper: corregidos 2 items`.
- **Causa raíz [INF]:** ejecuciones que nunca completan (ligado a D1/D2) quedan en estado corriendo hasta el tope de 120 min. El reaper corrige, pero el operador esperó 2 horas por trabajo muerto.
- **Mejora candidata a plan:** acortar el lazo de detección — cuando el watchdog mata un run (D2), transicionar el ticket asociado a `error`/`needs_review` inmediatamente en vez de esperar el timeout de 120 min del reaper. Severidad Alta, esfuerzo Medio.

### D4 — [MEDIO] Contradicción de vocabulario de estados: `needs_review` rechazado
- **Evidencia:** `stacky-2026-07-14.log` (clase ERROR)
  `claude code cli runtime failed: Estado inválido: 'needs_review'. Válidos: ['cancelled', 'completed', 'error', 'idle', 'running']`
- **Causa raíz [V]:** hay dos vocabularios de estado divergentes. La capa de completion produce `needs_review` (`services/agent_completion.py:44` → `TERMINAL_STATUSES = frozenset({"completed","error","cancelled","needs_review"})`), pero un validador de estado del runtime desplegado (v1.0.76) sólo acepta `[cancelled, completed, error, idle, running]` — sin `needs_review`. El resultado degradado a `needs_review` es rechazado como estado inválido.
- **Mejora candidata a plan:** unificar el enum de estados en una única fuente de verdad compartida entre completion y el validador del runtime; test de contrato que garantice que todo estado terminal producido por completion es aceptado por el validador. Severidad Media, esfuerzo Bajo/Medio. `[V]`

### D5 — [MEDIO] `pending-task.json` inválido: intake rechaza el artefacto
- **Evidencia:** `stacky-2026-07-14.log` (ERROR + 2 WARNING)
  `output_watcher mode_a: pending-task con fallo terminal ... epic-N/rf-N-filtros-cp-fecha-compromiso-pago-agenda/pending-task.json: intake rechazó el artefacto: JSON inválido tras reparaciones (...): Expecting value` y `pending-task: no se pudo parsear ...: Expecting value: line N column N`.
- **Causa raíz [INF]:** el agente escribió un `pending-task.json` con JSON inválido (patrón conocido: "crea archivos pero no la task"). El intake intenta reparar y falla terminal. La task no se crea.
- **Mejora candidata a plan:** endurecer la generación del `pending-task.json` (validar JSON antes de persistir en el runtime del agente) y/o mejorar el reparador de intake para el caso `Expecting value` (JSON vacío/truncado); exponer el archivo problemático en la UI para corrección 1-click. Severidad Media, esfuerzo Medio.

### D6 — [MEDIO] 502 en LLM local y en identidad ADO
- **Evidencia:** `stacky-2026-07-13.log:3922` `POST /api/llm/insights/1/generate ... 502`; `stacky-2026-07-14.log:15904,15909` `GET /api/tickets/ado-user?project=RSPACIFICO ... 502`.
- **Causa raíz [INF]:** el 502 de `/api/llm/insights` sugiere que el modelo local (Ollama/Qwen) no estaba disponible al generar insights; el 502 de `ado-user` correlaciona con la identidad ADO no resoluble (ver D9). El 502 llega a la UI sin degradación clara.
- **Mejora candidata a plan:** degradación explícita — devolver 200 con `available:false`/mensaje en vez de 502 cuando el LLM local o la identidad ADO no están disponibles, para no romper la UI. Severidad Media, esfuerzo Bajo.

### D7 — [BAJO] Config drift: `github_copilot_agents` inexistente (149×)
- **Evidencia:** `stacky-2026-07-13/14.log` (149 WARNING)
  `[stacky.config] agents_dir configurado para el proyecto activo no existe o no es carpeta: C:/desarrollo/.../DeployStackyAgents/github_copilot_agents. Uso la fuente canónica de Stacky Agents.`
- **Causa raíz [INF]:** un proyecto activo tiene configurado un `agents_dir` que no existe en el deploy; el sistema cae a la fuente canónica (correcto) pero lo advierte en cada resolución.
- **Mejora candidata a plan:** validar/limpiar `agents_dir` inválidos al activar proyecto y advertir UNA vez (dedup), no en cada ciclo. Severidad Baja, esfuerzo Bajo.

### D8 — [BAJO] `repo_root()` no resoluble: deploy congelado sin proyecto activo
- **Evidencia:** `stacky-2026-07-14.log` (2 WARNING)
  `[stacky.runtime_paths] repo_root() no resoluble: deploy congelado sin proyecto activo. Devuelvo sentinel inexistente (...__stacky_repo_root_unresolved__); los watchers no escanearán hasta que se active un proyecto con workspace_root.`
- **Causa raíz [V]:** por diseño el deploy congelado no tiene repo_root hasta activar un proyecto; hasta entonces los watchers no escanean. Es esperado, pero silenciosamente deja el sistema sin watchers.
- **Mejora candidata a plan:** superficie en la UI de "sin proyecto activo → watchers inactivos" como estado explícito (no sólo un WARNING en log). Severidad Baja, esfuerzo Bajo.

### D9 — [BAJO] Identidad ADO no resuelta: api-version bajo preview (11×)
- **Evidencia:** `stacky-2026-07-13/14.log` (11 WARNING)
  `[stacky_agents.ado_identity] No se pudo resolver identidad ADO para 'me': ADO GET .../_apis/connectionData?api-version=N.N → N: ... "The requested version ... is under preview. The -preview flag must be supplied ..."`
- **Causa raíz [INF]:** la llamada a `connectionData` usa una `api-version` que Azure DevOps marca como preview y exige el sufijo `-preview`. La identidad no resuelve → asignación automática se saltea y contribuye a los 502 de `ado-user` (D6).
- **Mejora candidata a plan:** corregir la `api-version` de `connectionData` (agregar `-preview` o bajar a una GA). Severidad Baja, esfuerzo Bajo.

---

## 4. Hallazgos DEV (ejecución local sin deploy)

> Nota: el log de DEV mezcla server real con corridas de pytest. Los hallazgos abajo excluyen ruido test-injected salvo donde el ruido MISMO es el hallazgo (V7).

### V1 — [ALTO] Bug de import: `from models import Execution` (318×)
- **Evidencia:** `stacky-*.log` (218 + 100 WARNING)
  `[stacky_agents.services.ado_edit_learning] sweep_recent_runs: error general: cannot import name 'Execution' from 'models' (...backend\models.py)`
- **Causa raíz [V]:** `services/ado_edit_learning.py:259` → `from models import Execution, session_scope`. En `models.py` la clase es `AgentExecution` (línea 207); no existe `Execution`. Cada barrido de `sweep_recent_runs` explota con ImportError.
- **Mejora candidata a plan:** corregir el import a `AgentExecution` (o al nombre real esperado) y agregar test que ejecute `sweep_recent_runs` sin mock del import. Severidad Alta, esfuerzo Muy bajo. `[V]`

### V2 — [ALTO] `outputs_dir` con ruta incorrecta → output_watcher ciego (4.761×)
- **Evidencia:** `stacky-*.log` (4.761 WARNING)
  `[stacky_agents.app] preflight: outputs_dir NO existe (C:\desarrollo\GIT\RS\Agentes\outputs) — el output_watcher no encontrará artifacts. Revisá proyecto activo / STACKY_REPO_ROOT.`
- **Causa raíz [INF]:** la ruta resuelta es `C:\desarrollo\GIT\RS\Agentes\outputs`, a la que le falta el segmento del proyecto (esperado `...\RSPACIFICO\Agentes\outputs`). La resolución de `outputs_dir`/`repo_root` produce una ruta mal formada cuando no hay proyecto activo o `STACKY_REPO_ROOT` correcto. El watcher no encuentra artifacts → los runs "no hacen nada".
- **Mejora candidata a plan:** validar la resolución de `outputs_dir` (nunca emitir una ruta sin el segmento de proyecto), y en dev sin proyecto activo NO advertir en cada ciclo. Severidad Alta, esfuerzo Bajo. Relacionado con D2/D8.

### V3 — [MEDIO] Sync ADO falla constantemente: PAT expirado / proyecto inexistente (~975×)
- **Evidencia:** `stacky-*.log` (887 + 54 WARNING PAT expirado, 34 WARNING proyecto inexistente)
  `sync ADO falló: ADO POST .../wiql → ... "Access Denied: The Personal Access Token used has expired."` y `"The following project does not exist: RSPACIFICO"`.
- **Causa raíz [INF]:** el PAT de ADO configurado en el entorno dev está expirado, y hay una configuración que apunta a un proyecto ADO llamado `RSPACIFICO` que no existe (el real parece ser `Strategist_Pacifico`). El sync corre en loop igual.
- **Mejora candidata a plan:** detectar PAT expirado y **desactivar el sync automático con backoff** (no reintentar cada ciclo generando 900+ warnings); superficie clara en la UI "PAT ADO expirado — renová en Caja Fuerte". Severidad Media, esfuerzo Bajo.

### V4 — [MEDIO] `CLAUDE_CODE_CLI_MODEL_FALLBACK` ausente crasheaba runs (16×) — riesgo latente en DEPLOY
- **Evidencia:** `stacky-*.log` (8 ERROR + 8 relacionados)
  `[stacky_agents.claude_code_cli] claude code cli runtime failed: 'Config' object has no attribute 'CLAUDE_CODE_CLI_MODEL_FALLBACK'`
- **Causa raíz [V]:** un run que necesita fallback de modelo accede a `Config.CLAUDE_CODE_CLI_MODEL_FALLBACK`. En el working tree actual **ya está corregido** (`backend/config.py:216`). Pero **el DEPLOY v1.0.76 (commit `7df192a8`, 2026-07-13) es anterior al fix** → riesgo latente de crash en producción si se dispara el fallback (no se observó disparado en los logs de deploy, pero el binario es vulnerable).
- **Mejora candidata a plan:** re-publicar el deploy con el fix ya presente en el working tree; agregar test que instancie `Config` y verifique presencia del atributo. Severidad Media, esfuerzo Bajo (mayormente release). `[V]`

### V5 — [MEDIO] `ado_edit_ledger`: SQLite "unable to open database file" (42×)
- **Evidencia:** `stacky-*.log` (30 + 12 WARNING)
  `[stacky_agents.services.ado_edit_ledger] ado_edit_ledger: no se pudo crear tabla SQLite: unable to open database file` y `... falló en mark_learned: unable to open database file`.
- **Causa raíz [INF]:** la ruta del archivo SQLite del ledger apunta a un directorio inexistente/no escribible (probablemente ligado a `repo_root`/`data_dir` mal resuelto, mismo tronco que V2). El ledger de ediciones ADO no persiste.
- **Mejora candidata a plan:** garantizar creación del directorio padre (`mkdir -p`) antes de abrir la DB del ledger y degradar a no-op silencioso (una advertencia, no 42). Severidad Media, esfuerzo Bajo.

### V6 — [MEDIO] Excepciones no manejadas en endpoints (reales, no-test)
- **Evidencia:** `stacky-*.log` (ERROR, excluyendo rutas pytest)
  `unhandled exception in GET /api/devops/console/conversations` (6×), `POST /api/devops/console/exec` (4×), `POST /api/agents/run` (4×), `GET /api/harness-flags` (3×), `POST /api/tickets/by-ado/N/create-child-task` (2×), `POST /api/ci/failure-webhook` (1×).
- **Causa raíz [NV]:** los mensajes no incluyen el traceback discriminado por endpoint en la línea agregada; requieren correlación con el traceback siguiente. Varias podrían ser transitorias, pero `devops/console/*` y `agents/run` aparecen repetidas.
- **Mejora candidata a plan:** instrumentar los handlers de `devops/console/*` y `agents/run` con captura de excepción + respuesta 4xx/5xx tipada y traceback correlacionado por `exec_id`/endpoint. Severidad Media, esfuerzo Medio. `[NV]` sobre causa puntual.

### V7 — [MEDIO] Log operativo contaminado por pytest (observabilidad)
- **Evidencia:** de 102 tracebacks en DEV, **91 contienen rutas `pytest-of-juanluca\pytest-N\`**; mensajes claramente sembrados por tests: `_load_last_project_confidence: error inesperado: DB exploded` (12×), `[copilot_bridge] claude_cli exit=N stderr=boom auth error` (2×), `stale-recovery cycle failed: no such table: tickets` (2×), quarantine de `test_watcher_intake_*`.
- **Causa raíz [V]:** las corridas de pytest escriben al MISMO archivo de log diario que el server local (`backend/data/logs/stacky-YYYY-MM-DD.log`). El log de dev deja de ser confiable para diagnóstico operativo (hay que filtrar manualmente el ruido de tests).
- **Mejora candidata a plan:** aislar el logging de tests (handler nulo o archivo separado bajo tmp) para que los runs de pytest no escriban en `data/logs/`; alternativamente, un flag `STACKY_TEST_MODE` que redirija el FileHandler. Severidad Media, esfuerzo Bajo. `[V]`

### V8 — [BAJO] Sync Jira saltado sin credenciales (448×)
- **Evidencia:** `stacky-*.log` (448 WARNING) `sync Jira saltado: Credenciales Jira no encontradas ...`.
- **Causa raíz [V]:** no hay credenciales Jira configuradas; el sync se saltea correctamente pero lo advierte en cada ciclo.
- **Mejora candidata a plan:** si Jira no está configurado, no correr el sync (o advertir una vez al arranque), no cada ciclo. Severidad Baja, esfuerzo Muy bajo.

---

## 5. Comparativa DEPLOY vs DEV

| Tema | Solo DEPLOY | Solo DEV | En AMBOS |
|---|---|---|---|
| `GET /api/v1/pipeline/status` 404 | — | — | Sí (10.687 dep / 12.094 dev) |
| Claude CLI workspace no confiado (D1) | Sí (bloqueante) | No (dev usa checkout confiado) | — |
| Stall watchdog mata runs (D2) | Sí (7 runs) | No observado | — |
| Reaper timeout 120 min (D3) | Sí (2 tickets) | No observado | — |
| `needs_review` estado inválido (D4) | Sí (v1.0.76 viejo) | No (working tree ya define el estado) | — |
| Import `Execution` roto (V1) | No (deploy no ejercita el path) | Sí (318×) | Latente en ambos (mismo código base) |
| `outputs_dir` mal resuelto (V2) | Parcial (repo_root sentinel, D8) | Sí (4.761×) | Tronco común de resolución de rutas |
| PAT ADO expirado (V3) | Menor (11× identidad) | Sí (975×) | Config de credenciales |
| Log contaminado por pytest (V7) | No (deploy no corre tests) | Sí | — |
| ANSI en archivo de log | Sí (6.590/día) | Sí | Sí (higiene de logs) |

**Lectura:** DEPLOY falla por **entorno/ejecución** (trust, stalls, timeouts, estados viejos) porque de verdad ejecuta agentes contra RSPACIFICO. DEV falla por **configuración/credenciales/bugs de código de bajo tráfico** (imports, rutas, PAT) y está enturbiado por tests. El **único gran problema compartido y de altísimo volumen es el 404 de `pipeline/status`** y la **higiene de logs** (ANSI + warnings repetidos sin dedup).

---

## 6. Mejoras propuestas (agrupadas por tema)

### A. Ejecución de agentes robusta (producción)
1. **Preflight de trust de workspace** para `claude_code_cli` (D1) — auto-set `hasTrustDialogAccepted` para el `workspace_root` activo o fallo temprano accionable.
2. **Cierre rápido de runs colgados** (D2+D3) — cuando el watchdog mata por stall, transicionar el ticket a `error`/`needs_review` de inmediato en vez de esperar 120 min del reaper.
3. **Unificar vocabulario de estados** (D4) — una sola fuente de verdad para estados terminales + test de contrato completion↔validador.

### B. Corrección de bugs de código (verificados)
4. **Fix import `Execution`→`AgentExecution`** en `ado_edit_learning.py:259` (V1) + test de `sweep_recent_runs`.
5. **Re-publicar deploy con `CLAUDE_CODE_CLI_MODEL_FALLBACK`** ya presente (V4) + test de atributo en `Config`.
6. **`mkdir -p` del directorio del SQLite ledger** (V5) antes de abrir la DB.

### C. Resolución de rutas / configuración
7. **Endurecer resolución de `outputs_dir`/`repo_root`** (V2+D8) — nunca emitir rutas sin segmento de proyecto; estado UI explícito "sin proyecto → watchers inactivos".
8. **Degradación de integraciones no configuradas** (V3+V8+D6) — PAT expirado / Jira ausente / LLM local ausente ⇒ desactivar el poll con backoff y superficie UI, no warnings/502 por ciclo.
9. **Corregir api-version de `connectionData`** en `ado_identity` (D9).

### D. Higiene y observabilidad de logs
10. **Route 404 masiva `pipeline/status`** (Sección 7, top #1) — implementar la ruta o eliminar/arreglar el cliente que la pollea.
11. **Strip ANSI en el FileHandler** — los colores de werkzeug no deben persistirse al archivo (6.590/día).
12. **Aislar logging de pytest** (V7) — tests no escriben en `data/logs/`.
13. **Dedup/rate-limit de warnings de preflight** — outputs_dir, PAT, Jira, agents_dir se repiten miles de veces; loguear una vez por cambio de estado.

---

## 7. TOP priorizado de candidatos a plan (para formalizar con `proponer-plan-stacky`)

Rankeado por (impacto en robustez × frecuencia observada) / esfuerzo.

| # | Candidato a plan | Hallazgos | Sev. | Esfuerzo | Por qué primero |
|---|---|---|---|---|---|
| 1 | **Ejecución confiable de Claude CLI en deploy: preflight de trust + cierre rápido de stalls/timeouts** | D1, D2, D3 | Crítico | Medio | Es el bloqueo real de producción: los runs mueren o cuelgan 2h. Sin esto, el deploy no ejecuta agentes. |
| 2 | **Silenciar y arreglar el 404 de `pipeline/status` + higiene de logs (ANSI, dedup, aislar pytest)** | 404, ANSI, V7, V3/V8 dedup | Alto | Bajo/Medio | 22.000+ líneas de ruido/día ocultan fallos reales; ROI enorme, esfuerzo bajo. |
| 3 | **Fix de bugs verificados de bajo esfuerzo: import `Execution`, SQLite ledger `mkdir`, re-deploy con fallback de modelo** | V1, V5, V4 | Alto | Muy bajo | Bugs `[V]` con fix trivial y test directo; quita 360+ warnings/errores. |
| 4 | **Resolución robusta de rutas de proyecto (`outputs_dir`/`repo_root`) + estado UI de watchers** | V2, D8 | Alto | Bajo | Causa raíz de "el run no hace nada" (watcher ciego); 4.761 warnings/día. |
| 5 | **Unificar vocabulario de estados y degradación de integraciones no configuradas (PAT/Jira/LLM local)** | D4, D6, V3, V8, D9 | Medio | Medio | Contrato de estados consistente + dejar de romper la UI con 502 y de floodear con reintentos. |

---

## 8. Anexos

### 8.1 Rutas y comandos usados (reproducción)

**Fuentes:**
- DEPLOY: `Stacky Agents/DeployStackyAgents/data/logs/stacky-2026-07-13.log`, `...-07-14.log`
- DEV: `Stacky Agents/backend/data/logs/stacky-2026-07-01.log` … `-07-15.log`

**Conteo de niveles / HTTP (por scope):**
```
grep -rhc " ERROR "   <dir>   # DEV: 104  | DEPLOY: 11
grep -rhc " WARNING " <dir>   # DEV: 7608 | DEPLOY: 224
grep -rhc "Traceback (most recent call last)" <dir>  # DEV: 102 | DEPLOY: 1
grep -rhoE '" 404 ' <dir> | wc -l   # DEV: 12103 | DEPLOY: 10706
grep -rhoE '" 50[23] ' <dir> | wc -l # DEV: 5 | DEPLOY: 3
```

**Clasificación de mensajes (normalizando dígitos a N):**
```
grep -rhE " WARNING " <dir> | sed -E 's/^[0-9-]+ [0-9:]+ WARNING //; s/[0-9]+/N/g' | sort | uniq -c | sort -rn | head
grep -rhE " ERROR "   <dir> | sed -E 's/^[0-9-]+ [0-9:]+ ERROR //;   s/[0-9]+/N/g' | sort | uniq -c | sort -rn | head
```

**Top rutas 404 (stripping ANSI):**
```
grep -rhoE '"[^"]*" 404' <dir> | sed -E 's/\[[0-9;]*m//g; s/\?[^"]*//; s/ HTTP\/1\.1//; s/^"//; s/" 404//' | sort | uniq -c | sort -rn | head
```

**Contaminación pytest (DEV):**
```
grep -rhc "pytest-of-juanluca" <dev_dir>   # 91 (de 102 tracebacks)
```

### 8.2 Verificaciones contra código (marca [V])
- `services/ado_edit_learning.py:259` → `from models import Execution, session_scope`
- `models.py:207` → `class AgentExecution(Base)` (no existe `Execution`)
- `config.py:216-217` → `CLAUDE_CODE_CLI_MODEL_FALLBACK = os.getenv("CLAUDE_CODE_CLI_MODEL_FALLBACK", "claude-sonnet-4-6")` (fix ya presente en working tree; ausente en deploy v1.0.76 / commit `7df192a8`)
- `services/agent_completion.py:44` → `TERMINAL_STATUSES = frozenset({"completed","error","cancelled","needs_review"})` (choca con validador del deploy que lista `[cancelled,completed,error,idle,running]`)
- `grep` de `v1/pipeline/status` en `backend/**.py`, `frontend/src`, `frontend/dist`, `vscode_extension` → **sin coincidencias**: la ruta no existe en el backend y el cliente que la pollea no está en el repo (poller externo/legacy o bundle minificado). `[INF]`

### 8.3 Notas de método y confianza
- Los conteos son sobre los archivos citados a la fecha de corte (2026-07-15 13:38).
- Muchas líneas ERROR de DEV son **test-injected** (`DB exploded`, `boom auth error`, rutas pytest); se excluyeron del análisis de fallos reales salvo donde el ruido mismo es el hallazgo (V7).
- No se pudo inspeccionar artifacts de runs (`outputs/` fuera del repo) ni logs de frontend (no persistidos): esos gaps limitan la profundidad de causa raíz en D5/V2/V6 (marcados `[INF]`/`[NV]`).
