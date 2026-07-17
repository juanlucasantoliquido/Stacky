# Plan 156 — Identidad de build, drift proceso-vs-repo y huellas de regresión

> **Estado:** PROPUESTO v1 (2026-07-16) · **Autor:** StackyArchitectaUltraEficientCode
> **Origen:** debate adversarial 2026-07-16 con auditoría empírica de los logs del deploy (07-14/07-16). El gap viene verificado del debate; toda la evidencia archivo:línea de este doc fue **re-verificada contra el worktree el 2026-07-16** y se corrigió el drift encontrado (ver §2 y el bloque "DRIFT CORREGIDO"). Los números de línea son referencia de ese día — **toda edición se ancla por TEXTO normativo citado, no por número de línea**.
> **Orden en el roadmap:** **cuarto**, después del plan del ledger de publicación transaccional, el del arnés veraz y el del latido único. Esfuerzo **S** (≈80% del sustrato ya existe): entra en cualquier hueco. Es **independiente** de los tres: ninguno lo bloquea ni él a ellos. Su catálogo de huellas (F4) es el **sustrato** que un futuro plan diferido de "análisis local de logs con clustering" consumiría.
> **Runtimes:** este plan es **identidad del BACKEND + un catálogo de datos + un chip de UI de observación**. Es **100% agnóstico del runtime de agentes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): ninguna fase toca el camino de ejecución de agentes ni el de publicación. La identidad de build es del proceso Flask, la misma para los 3 runtimes. La paridad de runtimes es automática por vacuidad. Se declara igual por fase.
> **Flags nuevas:** **NINGUNA.** Todo aditivo y backward-compatible: campos nuevos en un endpoint de lectura ya existente, un chip que aparece solo, una alerta que solo se muestra en dev, un evento de shutdown automático, y un catálogo de datos que nace poblado. NO se toca `FLAG_REGISTRY`, NO se toca `_CURATED_DEFAULTS_ON`, NO hay panel nuevo, NO hay config nueva del operador.
> **Human-in-the-loop:** la alerta de drift **AVISA, no actúa** — nunca reinicia el backend sola; el operador decide. El evento de shutdown solo REGISTRA. Ninguna decisión se le quita al operador.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** hoy pasó algo grave y silencioso. El server DEV corrió **todo el día código pre-fixes** — los logs del deploy muestran **~6.346 respuestas 404 de `GET /api/v1/pipeline/status`** y **~6.427 líneas contaminadas con secuencias ANSI**, DOS clases de error que el working tree **ya arregla** (el shim 200 y el strip de ANSI ya están en el código) — y **nada lo señaló**. El sistema no sabe qué versión de sí mismo está corriendo: un proceso puede quedar horas ejecutando un binario/código anterior al del repo sin que ninguna señal lo delate. Además, cuando ese deploy se apagó (07-14 18:20) lo hizo **sin dejar rastro** (corte abrupto, cero evento de shutdown), así que ni siquiera se puede reconstruir su ciclo de vida. Este plan instala la **memoria inmunológica** del sistema: hace que el proceso **DECLARE su identidad de build** (`source_commit` + `built_at`), **alerte el drift proceso-vs-repo** en dev (chip en el TopBar), **firme su shutdown** en `system_logs`, y mantenga un **catálogo determinista de "huellas"** de clases de error ya resueltas para **auto-detectar regresiones** en los logs frescos de cada deploy. El grueso ya existe (`services/app_version.py`, el `source_commit` horneado en `release-manifest.json`, el `version` en `/api/diag/health`): este plan **cierra los cabos sueltos** que faltan.

**KPIs binarios (comandos exactos). Backend: el `.venv` del worktree puede NO existir; los comandos de test se corren en el checkout principal `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con el venv real `backend\.venv\Scripts\python.exe` (py3.13; `backend/venv` NO existe). Equivalente POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend" && .venv/Scripts/python.exe -m pytest tests/<archivo> -q`. Frontend: desde `.../frontend` con `npx vitest run src/<archivo>`.**

- **KPI-1 — Identidad de build backend verde:** `.venv\Scripts\python.exe -m pytest tests/test_app_version_build_identity.py -q` → exit 0 (incluye el caso deploy con `release-manifest.json` de fixture y el caso dev con git; `source_commit` y `built_at` presentes en AMBOS modos).
- **KPI-2 — `/api/diag/health` expone identidad:** cubierto por `test_app_version_build_identity.py` (test que arma la app y hace `GET /api/diag/health` verificando que el body trae `source_commit`, `built_at`, `repo_head` y `build_drift`).
- **KPI-3 — Helpers puros del chip verdes:** `npx vitest run src/components/__tests__/buildIdentity.test.ts` → exit 0 (short-hash, formato de `built_at`, etiqueta del chip, y `driftBanner` visible sólo cuando `build_drift === true`).
- **KPI-4 — Evento de shutdown verde:** `.venv\Scripts\python.exe -m pytest tests/test_lifecycle_shutdown_log.py -q` → exit 0 (disparar el handler escribe **exactamente 1** fila `system_logs` con `source="app_lifecycle"`, `action="shutdown"` y el motivo en `context_json`).
- **KPI-5 — Schema del catálogo verde:** `.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_catalog.py -q` → exit 0 (JSON válido, sin ids duplicados, cada `log_pattern` compila como regex de Python, campos obligatorios presentes por entrada).
- **KPI-6 — Scanner de huellas verde:** `.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_scan.py -q` → exit 0 (una muestra "sucia" con una huella `resolved` matchea su id; un log "limpio" no matchea nada; el grep NEGATIVO se comporta binario).
- **KPI-7 — Tipos frontend verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-8 — Tests backend registrados en el arnés:** `grep -c "test_app_version_build_identity.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`; lo mismo para `test_lifecycle_shutdown_log.py`, `test_error_fingerprints_catalog.py` y `test_error_fingerprints_scan.py`.

**KPIs de impacto (proyectados, verificables por observación):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Tiempo de detección de drift proceso-vs-repo | horas / auditoría manual de logs | **inmediato** (chip + banner en el TopBar, sólo en dev) |
| Regresiones de clases de error ya resueltas | se descubren por arqueología de logs (o nunca) | detectadas por el smoke de huellas sobre los logs frescos del deploy |
| Trazabilidad del ciclo de vida del proceso | ninguna al apagar (corte abrupto sin rastro) | fila de `shutdown` firmada en `system_logs` con motivo |
| ¿El proceso sabe qué commit corre? | no | sí: `source_commit` + `built_at` en `/api/diag/health` y en el chip |

**Impacto esperado:** un operador (o un smoke automático) ve de un vistazo si el server corre código viejo; un deploy que reintroduce una clase de error ya matada **falla el smoke** en vez de correr silenciosamente todo el día; y el ciclo de vida del proceso queda auditable de arranque a apagado. Es la diferencia entre un sistema que **no sabe** qué es y uno que **declara** su identidad y **se auto-vigila**.

---

## 2. Por qué ahora / gap que cierra (evidencia verificada 2026-07-16)

### 2.1 L2 — Drift proceso-vs-repo sin ninguna señal

- El proceso Flask puede quedar horas corriendo código anterior al del repo. Hoy `GET /api/diag/health` (`backend/api/diag.py:311`, endpoint `health()`) devuelve `"version": get_app_version()` (`:400`) — **sólo** la versión de marketing (`VERSION.txt`/`package.json`), que **no cambia entre commits**. No hay forma de saber en qué commit se construyó/arrancó el proceso ni si el repo avanzó desde entonces.
- **DRIFT CORREGIDO respecto del debate:** el debate citó el `version` en `api/diag.py` "aprox :391"; en el worktree está en **`:400`** (el endpoint `health()` empieza en `:311`). Editar por TEXTO (`"version": get_app_version(),`), no por número.

### 2.2 El sustrato de identidad de build YA EXISTE (≈80% del trabajo hecho — verificado)

- `deployment/build_release.ps1:668-696` — el bloque "Generando metadata" **YA** captura el hash: `$gitSha = (git -C $appRoot rev-parse --short HEAD).Trim()` (`:671`) y lo hornea en el manifest como `source_commit = $gitSha` (`:681`), escrito a `release-manifest.json` (`:696`). **El hash se toma en build-time desde el repo; el deploy NO necesita `.git`.**
- **DRIFT CORREGIDO (clave):** el manifest **NO tiene un campo `built_at`**. Tiene **`generated_at = (Get-Date)...` (`:678`)**. Por lo tanto, para respetar "Fuera de scope: no tocar el pipeline de build más allá de leer el manifest ya generado", `built_at` se obtiene **leyendo `generated_at` del manifest** (NO se agrega un campo nuevo al build). El backend lo expone renombrado a `built_at`.
- `backend/services/app_version.py` — **YA** existe: `get_app_version()` (`:34`) con fuentes `VERSION.txt` → `package.json` → `"0.0.0-unknown"`, y **caché de módulo `_CACHED_VERSION`** (`:19`, `:37`). Este archivo es el lugar natural para sumar `source_commit`/`built_at` con el MISMO patrón de caché.
- `backend/runtime_paths.py` — `is_frozen()` (`:26`), `backend_root()` (`:30`), `app_root()` (`:36`). En deploy frozen, `app_root()` = carpeta padre del `backend/` que contiene el exe (`:41-43`), o sea la **raíz del release donde vive `release-manifest.json`**. En dev, `app_root()==backend_root()==.../backend` y **no hay** `release-manifest.json` → se cae a git.

### 2.3 L8 — Deploy apagado sin evento de shutdown (corte abrupto)

- El deploy v1.0.76 se apagó el 07-14 18:20 sin dejar rastro. No hay ninguna fila de "shutdown" en `system_logs`.
- El sustrato para escribirla **YA existe**: `backend/models.py:379` — `class SystemLog` (tabla `"system_logs"`, `:388`) con `level`/`source`/`action`/`context_json` (`:394-412`). Y `backend/services/stacky_logger.py:162` ya registra `atexit.register(self._flush_on_exit)` y `_flush_on_exit()` (`:425`) hace un `_persist_batch(...)` **síncrono en el main thread** — o sea, escribir a SQLAlchemy en atexit desde el main thread es un patrón **ya establecido y seguro** en este repo. Falta un handler que registre el **evento** de shutdown (no sólo drenar la cola).

### 2.4 L9 — Clases de error resueltas que podrían reaparecer (evidencia anclada)

Las clases de error ya resueltas hoy **no tienen ninguna guarda de regresión sobre los logs**. Un deploy que reintroduzca una de ellas correría silenciosamente. Anclaje verificado (para sembrar el catálogo de F4):

| # | Clase | Patrón de log (regex) | Estado | Matada por | Evidencia (archivo:línea) |
|---|---|---|---|---|---|
| 1 | 404 masivo de `/api/v1/pipeline/status` | `"GET /api/v1/pipeline/status[^"]*" 404` | **resolved** | plan de higiene de logs (145, commit `f00f161f`) | shim 200 en `backend/api/__init__.py:130-144`; supresión en `local_file_logging.py:68`; test `tests/test_plan145_pipeline_status_shim.py` |
| 2 | Secuencias ANSI en el log de archivo | `\x1b\[[0-9;]*m` | **resolved** | plan de higiene de logs (145) | `local_file_logging.py:42` (`_ANSI_RE`), `:49` (formatter), flag `STACKY_LOG_STRIP_ANSI` `:52`; test `tests/test_plan145_ansi_strip.py` |
| 3 | Tipo de work-item ADO inexistente (VS402323) | `VS402323: Work item type \S+ does not exist` | **open** (fix = plan del ledger de publicación transaccional, **aún no implementado**) | — | fixture `tests/test_create_child_task_endpoint.py:186-189` |
| 4 | 500 mudo / excepción no atrapada | `Traceback \(most recent call last\)` | **resolved** | plan de excepciones tipadas (149) + cero-errores-mudos (135) | `backend/api/errors.py:53-55` (`InternalError`), handler `backend/app.py:595-634`; test `tests/test_plan149_typed_errors.py` |
| 5 | Integración no configurada degradaba silenciosa | `"error_type"\s*:\s*"integration_unavailable"` | **resolved** | plan de degradación de integraciones (148) | `backend/api/errors.py:48-50`, breaker `backend/app.py:142`; test `tests/test_plan148_integration_degradation.py` |
| 6 | "Éxito fantasma": task de épica marcada creada pero inexistente en ADO | `task_not_found_in_ado` | **resolved** (guarda = quarantine) | G1.1 / cero-errores-mudos (135) | `backend/api/tickets.py:4931,4939,4943`; KPI `backend/services/harness_health.py:714-730`; test `tests/test_harness_health_integrity.py:171-184` |
| 7 | Claude CLI colgado/zombie | `stall watchdog: \d+s sin eventos del stream` | **resolved** | plan trust/estados Claude CLI (144) + cap de sesión (37) | `backend/services/claude_code_cli_runner.py:1348-1349`, cap `:1309`; timeout `backend/config.py:251` (1800s); test `tests/test_claude_stall_signal.py` |
| 8 | PM sin snapshot (404 esperado) | `"error"\s*:\s*"NO_SNAPSHOT"` | **by_design** (estado vacío esperado, NO regresión) | — | `backend/api/pm.py:303-308`; el frontend lo trata como no-error `frontend/src/pages/PMCommandCenter.tsx:866-868` |

- **DRIFT CORREGIDO (importante):** el debate listó "cliente fantasma live-pair/context" como una clase distinta. **NO es anclable**: `grep` global de `live-pair`/`live_pair`/`livepair` = **0 coincidencias** en código, docs y `data/logs`. El único cliente-fantasma con 404 masivo documentado es el poller de `/api/v1/pipeline/status` (= clase **#1**, consistente con los 6.346 404 de la tesis). **Se OMITE** del catálogo esa clase inventada; el catálogo nace con **8 clases reales ancladas** (las de la tabla). Si el implementador encuentra evidencia real de un endpoint "live-pair", que la agregue como entrada nueva — **jamás inventar el patrón**.
- **DRIFT CORREGIDO:** VS402323 (#3) **sigue ABIERTA** (su fix es el plan del ledger de publicación, aún no implementado): entra al catálogo con `status: "open"` (documentada, **NO** guardada por el smoke). NO_SNAPSHOT (#8) es un 404 **by-design** (estado vacío esperado): entra con `status: "by_design"` (documentada, **NO** guardada). El smoke NEGATIVO (F5) sólo alarma sobre huellas `status: "resolved"`.

### 2.5 Infra existente que se REUSA (leída, no supuesta)

| Símbolo | Archivo:línea (2026-07-16) | Rol en 156 |
|---|---|---|
| `get_app_version` + `_CACHED_VERSION` | `backend/services/app_version.py:19,34` | F1 agrega `get_source_commit`/`get_built_at`/`get_repo_head` con el MISMO patrón de caché de módulo. |
| `health()` + `"version"` | `backend/api/diag.py:311,400` | F1 agrega `source_commit`/`built_at`/`repo_head`/`build_drift` al MISMO dict de retorno. |
| `release-manifest.json` (`source_commit`, `generated_at`) | `deployment/build_release.ps1:681,678,696` | F1 lo LEE (no lo modifica); `generated_at` → `built_at`. |
| `is_frozen` / `app_root` / `backend_root` | `backend/runtime_paths.py:26,36,30` | F1 decide deploy-vs-dev y localiza el manifest / corre git en el repo. |
| `Health.get()` | `frontend/src/api/endpoints.ts:2689-2691` (pega a `/api/diag/health`) | F2 amplía el tipo de retorno; TopBar YA lo consume. |
| chip `styles.version` + estado `version` | `frontend/src/components/TopBar.tsx:40,102-106,213` | F2 enriquece el chip existente (short-hash + tooltip) y suma el banner de drift. |
| `SystemLog` | `backend/models.py:379-422` | F3 escribe una fila `shutdown`. |
| `atexit` + `_flush_on_exit` síncrono en main thread | `backend/services/stacky_logger.py:162,425` | F3 replica el patrón seguro (escritura síncrona en main thread al salir). |
| `session_scope` | `backend/db.py:302` | F3/F4/F5 abren sesión para escribir/leer. |
| `create_app()` + installs de handlers | `backend/app.py:232,240,244` | F3 llama `install_shutdown_hook()` junto a los otros installs. |
| `_ANSI_RE` / `_DEFAULT_SUPPRESSED_PATHS` | `backend/services/local_file_logging.py:42,68` | Fuente del patrón real de ANSI (#2) y del path 404 (#1) para el catálogo. |
| `logs_dir()` = `data_dir()/logs` (`stacky-*.log`) | `backend/services/local_file_logging.py:56,1-13` | F5: el smoke apunta acá para el grep de los logs frescos. |
| `smoke_test.ps1` (arranca el exe congelado, DB fresca) | `deployment/release_assets/smoke_test.ps1` | F5 lo COMPLEMENTA con un smoke de huellas separado (no lo reescribe). |
| `docs/sistema/*.md` (14 archivos, corpus del doc_indexer) | `Stacky Agents/docs/sistema/` | F4: el catálogo vive acá pero como **`.json`** (doc_indexer sólo escanea `*.md` — ver §4). |
| checklist red-team | `.claude/skills/criticar-y-mejorar-plan/SKILL.md:66-84` | F4 agrega UN ítem de convención (sin gate duro). |
| `HARNESS_TEST_FILES` (sh + ps1) | `backend/scripts/run_harness_tests.sh` y `.ps1` | Registro de los 4 tests backend nuevos. |

---

## 3. Principios y guardarraíles

1. **El proceso declara su identidad, no la infiere nadie.** La identidad de build (`source_commit` + `built_at`) sale del propio backend, cacheada al arranque; nadie tiene que adivinar qué corre.
2. **Reusar el sustrato, no reinventar.** `app_version.py` ya cachea; el manifest ya hornea el hash; `SystemLog` ya existe; el `atexit` síncrono en main thread ya es patrón. Este plan **conecta cabos**, no crea infraestructura nueva.
3. **No leer git por request.** `source_commit`/`built_at` se cachean a nivel módulo (una sola vez, como `_CACHED_VERSION`). El ÚNICO valor "vivo" es `repo_head` para detectar drift, y se cachea con **TTL corto (10 s)** — nunca por request (ver §4 y R3): una ráfaga de requests comparte una sola llamada a git.
4. **El drift AVISA, no actúa.** El banner de dev le dice al operador "reiniciá el backend"; **nunca** reinicia solo. Human-in-the-loop intacto.
5. **Sólo dev conoce el drift.** En deploy no hay `.git` → `repo_head` es `null` → `build_drift` es `false` siempre. El banner **nunca** aparece en deploy. Esto es correcto: en deploy la identidad es inmutable (horneada en el manifest).
6. **El catálogo es datos, no doc.** Vive como **`.json`** para NO contaminar el DocTree del `doc_indexer` (que escanea `docs/**/*.md`). Es la única fuente de verdad de los patrones; el scanner de Python y el smoke de PowerShell lo consumen, no lo duplican.
7. **Honestidad sobre lo que se puede detectar.** Un `kill -9` / corte de energía **no** dispara ningún handler (ni atexit ni signal): eso es física, no un bug. F3 captura los apagados **gráciles** (atexit, SIGTERM/SIGINT best-effort). La ausencia de un `shutdown` seguido de un `startup` nuevo es, de hecho, la evidencia de un corte abrupto.
8. **Sólo `resolved` se guarda.** El smoke NEGATIVO (F5) alarma únicamente sobre huellas `status: "resolved"`. Las `open` (VS402323) y `by_design` (NO_SNAPSHOT) se documentan pero **no** hacen fallar el smoke.
9. **Cero trabajo extra al operador.** Sin flags, sin config, backward-compatible: campos nuevos opcionales en un endpoint existente, un chip que aparece solo, un evento automático, un catálogo que nace poblado.
10. **No degradar.** git cacheado (module) + TTL (drift) ⇒ costo despreciable; el evento de shutdown es una fila; el smoke corre fuera del hot path. Ningún eje empeora.
11. **Mono-operador sin auth.** Nada de RBAC; los campos de `/api/diag/health` son de lectura y no validan `current_user`.
12. **Anti-gamear gates.** El smoke de F5 grepa **logs**, no el código ni este plan; el catálogo y sus tests contienen los patrones a propósito (esa es su función) y NO son escaneados por el smoke. Ver §9.

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **`source_commit`** | El hash corto de git del commit con el que se **construyó** (deploy) o **arrancó** (dev) el proceso. Es la identidad inmutable del build. En deploy sale de `release-manifest.json` (horneado en build-time); en dev, de `git rev-parse --short HEAD` cacheado al arranque. |
| **`built_at`** | Marca de tiempo de cuándo se generó el build. En deploy = el campo **`generated_at`** del manifest (¡ojo, el manifest NO tiene `built_at`, tiene `generated_at`!). En dev = fecha del commit `HEAD` (o `null`). |
| **`repo_head`** | El hash corto de `HEAD` del repo **ahora mismo** (valor vivo). Sólo en dev; en deploy es `null` (no hay `.git`). Cacheado con TTL corto. |
| **`release-manifest.json`** | El archivo que `build_release.ps1` escribe en la raíz del release con metadata del build (`source_commit`, `generated_at`, `version`, etc.). En el deploy vive en `app_root()`. El deploy NO necesita `.git`: el hash ya está horneado acá. |
| **drift proceso-vs-repo** | Situación en que el proceso corre un `source_commit` **distinto** del `repo_head` actual → el server está corriendo código viejo respecto del repo. Sólo detectable en dev. `build_drift = (repo_head != null && repo_head != source_commit)`. |
| **huella / fingerprint** | Una entrada del catálogo `error_fingerprints.json` que describe una **clase de error ya conocida**: id, patrón (regex) que la reconoce en un log, estado (`resolved`/`open`/`by_design`), qué plan la mató, y su test guardián. Es la "memoria inmunológica" del sistema. |
| **grep negativo** | Buscar un patrón esperando **NO encontrarlo**. El smoke de F5 grepa los logs frescos por cada huella `resolved`; si **encuentra** una, FALLA (la clase de error reapareció → regresión). |
| **DocTree / `doc_indexer`** | `backend/services/doc_indexer.py` escanea `docs/**/*.md` (`:270`) y arma el árbol de documentación navegable de la UI. **Sólo `*.md`.** Un `.json`/`.jsonl`/`.txt` bajo `docs/` es invisible para él — por eso el catálogo DEBE ser `.json`, nunca `.md` (un `.md` contaminaría el corpus RAG). |
| **TTL (time-to-live)** | Un valor cacheado que se considera válido durante N segundos; pasado ese lapso, se recalcula. `repo_head` usa TTL=10 s: muchos requests dentro de 10 s comparten una sola llamada a git. |
| **evento de shutdown** | Una fila en `system_logs` con `source="app_lifecycle"`, `action="shutdown"` y el motivo (`atexit`/`signal:15`/...) en `context_json`, escrita cuando el proceso se apaga grácilmente. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`backend/services/app_version.py`, `backend/api/diag.py`, `backend/app.py`, `backend/scripts/run_harness_tests.sh`, `backend/scripts/run_harness_tests.ps1`, `frontend/src/api/endpoints.ts`, `frontend/src/components/TopBar.tsx`, `frontend/src/components/TopBar.module.css`, `.claude/skills/criticar-y-mejorar-plan/SKILL.md`): `git status -- "<ruta>"`. Si hay WIP ajeno, STOP y avisar al orquestador (sesiones paralelas en el mismo árbol son un escenario real conocido). Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** backend SIEMPRE por archivo desde el checkout principal `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (el `.venv` del worktree `C:/wt/uxlog` puede no existir; correr en el checkout real). Frontend SIEMPRE por archivo con `npx vitest run src/<archivo>`. NUNCA suite completa en un solo proceso: cross-file pollution conocida y documentada en este repo, en ambos lados.
>
> **Orden de implementación:** F1 → F2 → F3 → F4 → F5 (F2 consume los campos que agrega F1; F5 consume el catálogo que crea F4; F3 es independiente). Ver §6.

---

### F1 — Identidad de build en `app_version.py` y en `GET /api/diag/health`

**Objetivo (1 frase):** que el backend declare `source_commit` y `built_at` (leídos del manifest en deploy, de git cacheado en dev) y los exponga —junto a `repo_head` y `build_drift`— en `/api/diag/health`. **Valor:** el proceso deja de ser anónimo; cualquiera (humano o smoke) sabe qué commit corre y si es viejo respecto del repo.

**Archivos:**
- MODIFICADO `backend/services/app_version.py` (nuevas funciones + cachés de módulo)
- MODIFICADO `backend/api/diag.py` (nuevos campos en el dict de `health()`)
- NUEVO `backend/tests/test_app_version_build_identity.py`
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el test)

**Paso 1 — `app_version.py`.** Agregar al final del módulo (respetando el patrón de caché de `_CACHED_VERSION`):

```python
import subprocess
import time

_CACHED_SOURCE_COMMIT: str | None = None
_SOURCE_COMMIT_RESOLVED = False   # distinguir "no resuelto aun" de "resuelto a None"
_CACHED_BUILT_AT: str | None = None
_BUILT_AT_RESOLVED = False
_REPO_HEAD_CACHE: tuple[float, str | None] | None = None   # (timestamp, value)
_REPO_HEAD_TTL_SECONDS = 10.0


def _release_manifest_path() -> Path:
    """release-manifest.json vive en la raiz del release (app_root en deploy)."""
    from runtime_paths import app_root
    return app_root() / "release-manifest.json"


def _read_manifest() -> dict | None:
    try:
        p = _release_manifest_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("app_version: manifest no legible: %s", exc)
    return None


def _git_short_head() -> str | None:
    """git rev-parse --short HEAD en el repo (solo dev). None si no hay git."""
    from runtime_paths import backend_root
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(backend_root()), capture_output=True, text=True, timeout=3,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001 (FileNotFoundError si no hay git, timeout, etc.)
        logger.debug("app_version: git rev-parse fallo: %s", exc)
    return None


def get_source_commit() -> str | None:
    """Identidad del build: manifest en deploy, git cacheado en dev. Cache de modulo."""
    global _CACHED_SOURCE_COMMIT, _SOURCE_COMMIT_RESOLVED
    if _SOURCE_COMMIT_RESOLVED:
        return _CACHED_SOURCE_COMMIT
    manifest = _read_manifest()
    if manifest and manifest.get("source_commit"):
        _CACHED_SOURCE_COMMIT = str(manifest["source_commit"]).strip() or None
    else:
        _CACHED_SOURCE_COMMIT = _git_short_head()
    _SOURCE_COMMIT_RESOLVED = True
    return _CACHED_SOURCE_COMMIT


def get_built_at() -> str | None:
    """built_at: manifest['generated_at'] en deploy; fecha del commit en dev. Cache de modulo."""
    global _CACHED_BUILT_AT, _BUILT_AT_RESOLVED
    if _BUILT_AT_RESOLVED:
        return _CACHED_BUILT_AT
    manifest = _read_manifest()
    if manifest and manifest.get("generated_at"):
        _CACHED_BUILT_AT = str(manifest["generated_at"]).strip() or None
    else:
        from runtime_paths import backend_root
        try:
            out = subprocess.run(
                ["git", "show", "-s", "--format=%cI", "HEAD"],
                cwd=str(backend_root()), capture_output=True, text=True, timeout=3,
            )
            _CACHED_BUILT_AT = out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None
        except Exception:  # noqa: BLE001
            _CACHED_BUILT_AT = None
    _BUILT_AT_RESOLVED = True
    return _CACHED_BUILT_AT


def get_repo_head() -> str | None:
    """HEAD vivo del repo (solo dev), con TTL corto. En deploy (frozen o con manifest) => None."""
    from runtime_paths import is_frozen
    if is_frozen() or _read_manifest() is not None:
        return None  # deploy: no hay drift posible (identidad inmutable)
    global _REPO_HEAD_CACHE
    now = time.monotonic()
    if _REPO_HEAD_CACHE is not None and (now - _REPO_HEAD_CACHE[0]) < _REPO_HEAD_TTL_SECONDS:
        return _REPO_HEAD_CACHE[1]
    value = _git_short_head()
    _REPO_HEAD_CACHE = (now, value)
    return value


def get_build_drift() -> bool:
    """True solo si el HEAD vivo difiere del source_commit del proceso (solo dev)."""
    head = get_repo_head()
    src = get_source_commit()
    return bool(head and src and head != src)
```

- **Caso borde:** en dev sin git instalado, `_git_short_head()` devuelve `None` → `source_commit=None`, `repo_head=None`, `build_drift=False` (no rompe nada). En deploy sin manifest (build viejo), `source_commit` cae a git (que tampoco está) → `None`. Todos los caminos degradan a `None`, nunca lanzan.
- **`_read_manifest()` se llama en `get_repo_head`** por request potencialmente: es un `Path.exists()` + `read_text` chico y sólo en dev; si preocupa, cachear el "¿hay manifest?" a nivel módulo. Aceptable como está (dev-only, archivo minúsculo).

**Paso 2 — `diag.py`.** En el dict de retorno de `health()` (ancla de texto: la línea `"version": get_app_version(),`, `:400`), agregar inmediatamente debajo:

```python
        "version": get_app_version(),
        "source_commit": get_source_commit(),   # Plan 156 F1 — identidad de build
        "built_at": get_built_at(),              # Plan 156 F1
        "repo_head": get_repo_head(),            # Plan 156 F1 — solo dev (None en deploy)
        "build_drift": get_build_drift(),        # Plan 156 F1 — solo dev
```

Ampliar el import existente `from services.app_version import get_app_version` (`:36`) a `from services.app_version import get_app_version, get_source_commit, get_built_at, get_repo_head, get_build_drift`.

**Paso 3 — Test** `backend/tests/test_app_version_build_identity.py` (DB real en memoria; patrón `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` ANTES de importar la app; monkeypatch para simular deploy vs dev):

| Test | Qué afirma |
|---|---|
| `test_deploy_lee_manifest` | Con `monkeypatch` de `app_version._release_manifest_path` a un JSON de fixture `{"source_commit":"abc1234","generated_at":"2026-07-14 18:00:00"}` (y reseteo de las cachés `_SOURCE_COMMIT_RESOLVED=False`/`_BUILT_AT_RESOLVED=False`), `get_source_commit()=="abc1234"` y `get_built_at()=="2026-07-14 18:00:00"`. |
| `test_dev_usa_git` | Sin manifest (monkeypatch `_read_manifest`→`None`) y con `_git_short_head` monkeypatcheado a `"deadbee"`, `get_source_commit()=="deadbee"`. |
| `test_drift_true_cuando_head_difiere` | monkeypatch `is_frozen`→`False`, `_read_manifest`→`None`, `get_source_commit`→`"aaa1111"`, `_git_short_head`→`"bbb2222"` (reset del TTL `_REPO_HEAD_CACHE=None`) → `get_build_drift() is True`. |
| `test_drift_false_en_deploy` | monkeypatch `is_frozen`→`True` → `get_repo_head() is None` y `get_build_drift() is False` (no hay drift en deploy). |
| `test_health_expone_campos` | Armar la app (`create_app()`), `client.get("/api/diag/health")` → 200 y el body tiene las claves `source_commit`, `built_at`, `repo_head`, `build_drift`. |

(Nota para el implementador: como las cachés son de módulo, cada test que las use debe **resetearlas** al inicio, p. ej. `app_version._SOURCE_COMMIT_RESOLVED = False`. Documentarlo con un `pytest.fixture(autouse=True)` que resetee las 5 cachés.)

**Paso 4 — Registrar** `tests/test_app_version_build_identity.py` en `run_harness_tests.sh` (`  tests/test_app_version_build_identity.py`) Y `.ps1` (`  "tests/test_app_version_build_identity.py"`), en un bloque nuevo (sh: `  # — Plan 156 · Identidad de build y huellas —`; ps1: `  # Plan 156 - Identidad de build y huellas`).

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_app_version_build_identity.py -q` → exit 0; `grep -c "test_app_version_build_identity.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`.

**Flag:** ninguna. **Runtimes:** identidad del backend; los 3 runtimes ven el mismo endpoint. **Fallback:** todo campo degrada a `None`/`False` si falta git o manifest — nunca rompe. **Trabajo del operador: ninguno.**

---

### F2 — Chip de versión + short-hash en el TopBar + alerta de drift (sólo dev)

**Objetivo (1 frase):** enriquecer el chip de versión existente del TopBar con el short-hash (`v1.0.76 · a1b2c3d`, tooltip con `built_at`) y mostrar un banner de drift **sólo cuando `build_drift === true`**. **Valor:** el operador ve de un vistazo qué corre y si es viejo, sin abrir logs.

**Archivos:**
- MODIFICADO `frontend/src/api/endpoints.ts` (ampliar el tipo de retorno de `Health.get`)
- NUEVO `frontend/src/components/buildIdentity.ts` (helpers PUROS)
- NUEVO `frontend/src/components/__tests__/buildIdentity.test.ts`
- MODIFICADO `frontend/src/components/TopBar.tsx` (consumir los campos + banner)
- MODIFICADO `frontend/src/components/TopBar.module.css` (clase del hash + clase del banner)

**Paso 1 — `endpoints.ts`.** Ampliar el tipo de retorno de `Health.get` (ancla: `get: (): Promise<{ version?: string; ok?: boolean; healthy?: boolean; shell_v2_enabled?: boolean }>`, `:2690-2691`) sumando los 4 campos opcionales, en AMBOS lados (la firma y el genérico de `api.get`):

```ts
get: (): Promise<{ version?: string; ok?: boolean; healthy?: boolean; shell_v2_enabled?: boolean;
                   source_commit?: string | null; built_at?: string | null;
                   repo_head?: string | null; build_drift?: boolean }> =>
  api.get<{ version?: string; ok?: boolean; healthy?: boolean; shell_v2_enabled?: boolean;
            source_commit?: string | null; built_at?: string | null;
            repo_head?: string | null; build_drift?: boolean }>("/api/diag/health"),
```

**Paso 2 — `frontend/src/components/buildIdentity.ts` (100% puro, sin JSX):**

```ts
export interface BuildIdentity {
  version: string | null;
  sourceCommit: string | null;
  builtAt: string | null;
  drift: boolean;
}

/** Etiqueta del chip: "v1.0.76 · a1b2c3d" (o "dev@local" si no hay version). */
export function versionChipLabel(b: BuildIdentity): string {
  const v = b.version ? `v${b.version}` : "dev@local";
  const h = b.sourceCommit ? ` · ${shortHash(b.sourceCommit)}` : "";
  return `${v}${h}`;
}

/** Short-hash defensivo (el backend ya manda short, pero por si llega largo). */
export function shortHash(commit: string | null | undefined): string {
  return commit ? commit.slice(0, 7) : "";
}

/** Tooltip del chip: incluye built_at legible. */
export function buildTooltip(b: BuildIdentity): string {
  const parts: string[] = [];
  parts.push(b.version ? `Versión ${b.version}` : "dev@local");
  if (b.sourceCommit) parts.push(`commit ${shortHash(b.sourceCommit)}`);
  if (b.builtAt) parts.push(`build ${b.builtAt}`);
  return parts.join(" · ");
}

/** Texto del banner de drift (sólo se muestra si drift === true). */
export function driftMessage(b: BuildIdentity): string {
  return `El servidor está corriendo código anterior al del repo (commit ${shortHash(b.sourceCommit)}). ` +
         `Reiniciá el backend para tomar los últimos cambios.`;
}
```

**Paso 3 — `TopBar.tsx`.** Cambiar el estado y el fetch existentes:
- Reemplazar `const [version, setVersion] = useState<string | null>(null);` (`:40`) por `const [build, setBuild] = useState<BuildIdentity>({ version: null, sourceCommit: null, builtAt: null, drift: false });`.
- En el `useEffect` del health (`:102-106`), setear todo: 

```ts
useEffect(() => {
  Health.get()
    .then((res) => setBuild({
      version: res.version ?? null,
      sourceCommit: res.source_commit ?? null,
      builtAt: res.built_at ?? null,
      drift: res.build_drift === true,
    }))
    .catch(() => { /* ignorar: no crítico */ });
}, []);
```

- Reemplazar el chip (`:213`) por:

```tsx
<span className={styles.version} title={buildTooltip(build)}>{versionChipLabel(build)}</span>
```

- Justo después del `<header>` de apertura o dentro de `styles.actions`, agregar el banner de drift (sólo dev; en deploy `build.drift` es siempre `false`):

```tsx
{build.drift && (
  <div className={styles.driftBanner} role="alert">{driftMessage(build)}</div>
)}
```

- Importar de `./buildIdentity`: `import { versionChipLabel, buildTooltip, driftMessage, type BuildIdentity } from "./buildIdentity";`.

**Paso 4 — `TopBar.module.css`.** Agregar `.driftBanner` (usar tokens de `theme.css`, colores de warning; ejemplo de forma, sin inline-style): un bloque visible arriba del bar con fondo de advertencia y texto contrastante. NO usar `style={{}}` en el `.tsx` (gotcha uiDebtRatchet). Si el hash necesita un color atenuado, agregar `.versionHash` (opcional).

**Paso 5 — Test** `frontend/src/components/__tests__/buildIdentity.test.ts` (100% puro, sin `render()`):

| Test | Qué afirma |
|---|---|
| `test_chip_label_con_hash` | `versionChipLabel({version:"1.0.76",sourceCommit:"a1b2c3d4e",builtAt:null,drift:false})` → `"v1.0.76 · a1b2c3d"`. |
| `test_chip_label_dev` | `versionChipLabel({version:null,sourceCommit:null,builtAt:null,drift:false})` → `"dev@local"`. |
| `test_tooltip_incluye_built_at` | `buildTooltip({version:"1.0.76",sourceCommit:"a1b2c3d",builtAt:"2026-07-14 18:00",drift:false})` contiene `"build 2026-07-14 18:00"` y `"commit a1b2c3d"`. |
| `test_short_hash` | `shortHash("a1b2c3d4e5f6")==="a1b2c3d"`; `shortHash(null)===""`. |
| `test_drift_message` | `driftMessage({...,sourceCommit:"a1b2c3d",drift:true})` contiene `"a1b2c3d"` y `"Reiniciá el backend"`. |

(El "banner visible sólo si drift" se cubre por la lógica pura: el `.tsx` renderiza el banner sólo cuando `build.drift`; como no hay RTL/jsdom, se verifica por `tsc` + smoke manual. El helper `driftMessage` es el único con lógica testeable.)

**Criterio de aceptación BINARIO:** `npx vitest run src/components/__tests__/buildIdentity.test.ts` → exit 0; `npx tsc --noEmit` → exit 0. **Verificación manual (documentada, sin operador):** en dev, arrancar el backend, hacer un commit nuevo en el repo, esperar >10 s (TTL), recargar la UI → aparece el banner de drift; reiniciar el backend → el banner desaparece.

**Flag:** ninguna. **Runtimes:** UI compartida; el chip muestra la identidad del backend, igual para los 3 runtimes. **Fallback:** si `/api/diag/health` no trae los campos (backend viejo), `build` queda con `null`/`false` y el chip cae a `dev@local` sin hash (backward-compatible). **Trabajo del operador: ninguno.**

---

### F3 — Evento de shutdown estructurado en `system_logs`

**Objetivo (1 frase):** registrar una fila `system_logs` (`source="app_lifecycle"`, `action="shutdown"`, motivo en `context_json`) cuando el proceso se apaga grácilmente (atexit / SIGTERM / SIGINT). **Valor:** el ciclo de vida del proceso queda auditable; un arranque sin un shutdown previo delata un corte abrupto (L8).

**Archivos:**
- NUEVO `backend/services/lifecycle_log.py` (`log_shutdown` síncrono idempotente + `install_shutdown_hook`)
- MODIFICADO `backend/app.py` (llamar `install_shutdown_hook()` en `create_app()`)
- NUEVO `backend/tests/test_lifecycle_shutdown_log.py`
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el test)

**Paso 1 — `backend/services/lifecycle_log.py`:**

```python
"""Plan 156 F3 — evento de shutdown estructurado en system_logs.

Escribe UNA fila al apagarse el proceso grácilmente (atexit / SIGTERM / SIGINT).
Escritura SINCRONA en el main thread (mismo patron seguro que
stacky_logger._flush_on_exit). Un kill -9 / corte de energia NO dispara nada:
eso es fisica, no un bug (ver plan, principio 7)."""
from __future__ import annotations

import atexit
import json
import logging
import os

logger = logging.getLogger("stacky.services.lifecycle_log")

_LOGGED = False       # idempotencia: una sola fila por proceso
_INSTALLED = False    # registrar hooks una sola vez


def log_shutdown(reason: str) -> None:
    """Escribe (una sola vez) la fila de shutdown. Nunca lanza (no bloquea el apagado)."""
    global _LOGGED
    if _LOGGED:
        return
    _LOGGED = True
    try:
        from db import session_scope
        from models import SystemLog
        from services.app_version import get_app_version, get_source_commit
        ctx = json.dumps({
            "reason": reason,
            "pid": os.getpid(),
            "version": get_app_version(),
            "source_commit": get_source_commit(),
        })
        with session_scope() as session:
            session.add(SystemLog(
                level="INFO", source="app_lifecycle", action="shutdown", context_json=ctx,
            ))
    except Exception as exc:  # noqa: BLE001 — jamas bloquear el apagado
        logger.debug("lifecycle_log: no se pudo registrar shutdown: %s", exc)


def install_shutdown_hook() -> None:
    """Registra atexit (siempre) + SIGTERM/SIGINT (best-effort). Idempotente."""
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    atexit.register(lambda: log_shutdown("atexit"))
    try:
        import signal
        for sig in (signal.SIGTERM, signal.SIGINT):
            prev = signal.getsignal(sig)

            def _handler(signum, frame, _prev=prev):
                log_shutdown(f"signal:{signum}")
                if callable(_prev) and _prev not in (signal.SIG_DFL, signal.SIG_IGN):
                    _prev(signum, frame)
                else:
                    raise SystemExit(0)

            signal.signal(sig, _handler)
    except (ValueError, OSError) as exc:  # no es main thread / SIGTERM limitado en Windows
        logger.debug("lifecycle_log: signals no instalables: %s", exc)
```

- **Nota Windows/frozen:** en Windows `SIGTERM` es limitado y un `taskkill /F` no lo dispara; atexit cubre el apagado normal y el `SystemExit`. Es best-effort **a propósito** (ver principio 7). El `raise SystemExit(0)` asegura que, tras registrar, el proceso efectivamente termine cuando no había handler previo.
- **Idempotencia:** `_LOGGED` evita doble fila si atexit y una señal disparan ambos.

**Paso 2 — `app.py`.** En `create_app()` (`:232`), junto a los otros installs (`install_file_log_handler()` `:240`, `install_console_log_handler()` `:244`), agregar:

```python
    from services.lifecycle_log import install_shutdown_hook
    install_shutdown_hook()   # Plan 156 F3 — firmar el shutdown en system_logs
```

`create_app()` corre en el main thread al importar (`app = create_app()`, `:704`), así que `signal.signal` es válido. Con el reloader de Flask dev, `create_app` puede correr en un proceso hijo; el `except (ValueError, OSError)` cubre el caso de no-main-thread sin romper.

**Paso 3 — Test** `backend/tests/test_lifecycle_shutdown_log.py` (DB real en memoria; `init_db()`):

| Test | Qué afirma |
|---|---|
| `test_log_shutdown_escribe_fila` | Reset `lifecycle_log._LOGGED = False`; `log_shutdown("test")`; query `SystemLog` filtrando `source=="app_lifecycle"`, `action=="shutdown"` → **exactamente 1** fila; `json.loads(row.context_json)["reason"]=="test"` y `["pid"]==os.getpid()`. |
| `test_log_shutdown_idempotente` | Reset `_LOGGED=False`; llamar `log_shutdown("a")` y luego `log_shutdown("b")` → sigue habiendo **1** sola fila con `reason=="a"` (la segunda es no-op). |
| `test_install_idempotente` | `install_shutdown_hook()` dos veces no lanza y deja `_INSTALLED is True` (no cuenta handlers, sólo que no rompe). |
| `test_log_shutdown_no_lanza_sin_db` | Con `session_scope` monkeypatcheado para lanzar, `log_shutdown("x")` **no** propaga la excepción (nunca bloquea el apagado). |

**Paso 4 — Registrar** `tests/test_lifecycle_shutdown_log.py` en el bloque Plan 156 de `run_harness_tests.sh` y `.ps1`.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_lifecycle_shutdown_log.py -q` → exit 0; `grep -c "test_lifecycle_shutdown_log.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`.

**Flag:** ninguna. **Runtimes:** ciclo de vida del backend; agnóstico del runtime de agentes. **Fallback:** si la DB no está disponible al salir, se degrada silenciosamente (no bloquea el apagado). **Trabajo del operador: ninguno.**

---

### F4 — Catálogo de huellas `error_fingerprints.json` + schema-test + ítem en la skill de crítica

**Objetivo (1 frase):** crear el catálogo determinista de las 8 clases de error ancladas (id, patrón, estado, plan que la mató, fecha, test guardián), validarlo con un schema-test, y sumar a la skill `criticar-y-mejorar-plan` un ítem de convención "¿registra su huella de regresión?" (SIN gate duro). **Valor:** la memoria inmunológica del sistema queda materializada y versionada, lista para que F5 y un futuro plan de análisis de logs la consuman.

**Archivos:**
- NUEVO `Stacky Agents/docs/sistema/error_fingerprints.json` (**`.json`**, NUNCA `.md` — ver §4/§9)
- NUEVO `backend/tests/test_error_fingerprints_catalog.py`
- MODIFICADO `.claude/skills/criticar-y-mejorar-plan/SKILL.md` (un ítem de checklist)
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el test)

**Paso 1 — `Stacky Agents/docs/sistema/error_fingerprints.json`.** Estructura (sembrar con las 8 clases de la tabla §2.4; los `pattern` se escriben con `\\` para que el JSON decodifique al regex correcto; cada entrada trae un `self_test` con muestras que el scanner de F5 usará):

```json
{
  "schema_version": 1,
  "description": "Catalogo de huellas de clases de error ya conocidas de Stacky Agents. status=resolved => el smoke de huellas alarma si el patron REAPARECE en un log fresco (regresion). status=open/by_design => documentada, NO guardada.",
  "fingerprints": [
    {
      "id": "pipeline_status_404",
      "title": "404 masivo de /api/v1/pipeline/status",
      "class": "http-404-poller",
      "status": "resolved",
      "log_pattern": "\"GET /api/v1/pipeline/status[^\"]*\" 404",
      "log_guarded": true,
      "killed_by": "plan 145 (higiene/observabilidad de logs)",
      "killed_commit": "f00f161f",
      "date_resolved": "2026-07-16",
      "guard_test": "tests/test_plan145_pipeline_status_shim.py",
      "evidence": "backend/api/__init__.py:130-144; backend/services/local_file_logging.py:68",
      "self_test": {
        "matches": ["127.0.0.1 - - [14/Jul/2026 18:00:00] \"GET /api/v1/pipeline/status HTTP/1.1\" 404 -"],
        "clean":   ["127.0.0.1 - - [16/Jul/2026 10:00:00] \"GET /api/v1/pipeline/status HTTP/1.1\" 200 -"]
      }
    },
    {
      "id": "ansi_in_file_log",
      "title": "Secuencias ANSI en el log de archivo",
      "class": "log-formatting",
      "status": "resolved",
      "log_pattern": "\\x1b\\[[0-9;]*m",
      "log_guarded": true,
      "killed_by": "plan 145 (higiene/observabilidad de logs)",
      "killed_commit": "f00f161f",
      "date_resolved": "2026-07-16",
      "guard_test": "tests/test_plan145_ansi_strip.py",
      "evidence": "backend/services/local_file_logging.py:42,49,52",
      "self_test": {
        "matches": ["2026-07-14 18:00:00 INFO [32mverde[0m arranque"],
        "clean":   ["2026-07-16 10:00:00 INFO verde arranque"]
      }
    },
    {
      "id": "ado_workitem_type_vs402323",
      "title": "Tipo de work-item ADO inexistente (VS402323)",
      "class": "ado-publish",
      "status": "open",
      "log_pattern": "VS402323: Work item type \\S+ does not exist",
      "log_guarded": false,
      "killed_by": "pendiente — plan del ledger de publicacion transaccional (aun no implementado)",
      "killed_commit": null,
      "date_resolved": null,
      "guard_test": "tests/test_create_child_task_endpoint.py",
      "evidence": "backend/tests/test_create_child_task_endpoint.py:186-189",
      "self_test": {
        "matches": ["ERROR ado_publisher VS402323: Work item type Feature does not exist in project X"],
        "clean":   ["INFO ado_publisher created work item type Task"]
      }
    },
    {
      "id": "muted_500_untyped",
      "title": "500 mudo / excepcion no atrapada",
      "class": "error-envelope",
      "status": "resolved",
      "log_pattern": "Traceback \\(most recent call last\\)",
      "log_guarded": false,
      "killed_by": "plan 149 (excepciones tipadas) + plan 135 (cero errores mudos)",
      "killed_commit": "5d091726",
      "date_resolved": "2026-07-16",
      "guard_test": "tests/test_plan149_typed_errors.py",
      "evidence": "backend/api/errors.py:53-55; backend/app.py:595-634",
      "self_test": {
        "matches": ["Traceback (most recent call last):"],
        "clean":   ["ERROR api typed 500 [type=internal exec_id=42]"]
      }
    },
    {
      "id": "integration_silent_degradation",
      "title": "Integracion no configurada degradaba silenciosa",
      "class": "integration",
      "status": "resolved",
      "log_pattern": "\"error_type\"\\s*:\\s*\"integration_unavailable\"",
      "log_guarded": false,
      "killed_by": "plan 148 (degradacion de integraciones)",
      "killed_commit": "af938ffe",
      "date_resolved": "2026-07-16",
      "guard_test": "tests/test_plan148_integration_degradation.py",
      "evidence": "backend/api/errors.py:48-50; backend/app.py:142",
      "self_test": {
        "matches": ["{\"error_type\": \"integration_unavailable\", \"integration\": \"ado\"}"],
        "clean":   ["{\"ok\": true}"]
      }
    },
    {
      "id": "epic_task_phantom_success",
      "title": "Exito fantasma: task de epica marcada creada pero inexistente en ADO",
      "class": "publish-integrity",
      "status": "resolved",
      "log_pattern": "task_not_found_in_ado",
      "log_guarded": false,
      "killed_by": "G1.1 / plan 135 (cero errores mudos)",
      "killed_commit": null,
      "date_resolved": "2026-07-15",
      "guard_test": "tests/test_harness_health_integrity.py",
      "evidence": "backend/api/tickets.py:4931,4939,4943; backend/services/harness_health.py:714-730",
      "self_test": {
        "matches": ["WARN tickets quarantine reason=task_not_found_in_ado exec_id=7"],
        "clean":   ["INFO tickets task created ok"]
      }
    },
    {
      "id": "claude_cli_zombie_stall",
      "title": "Claude CLI colgado/zombie",
      "class": "runtime-liveness",
      "status": "resolved",
      "log_pattern": "stall watchdog: \\d+s sin eventos del stream",
      "log_guarded": false,
      "killed_by": "plan 144 (trust/estados Claude CLI) + plan 37 (cap de sesion)",
      "killed_commit": "da6d3609",
      "date_resolved": "2026-07-16",
      "guard_test": "tests/test_claude_stall_signal.py",
      "evidence": "backend/services/claude_code_cli_runner.py:1348-1349,1309; backend/config.py:251",
      "self_test": {
        "matches": ["WARN claude R1.1 stall watchdog: 120s sin eventos del stream — terminando"],
        "clean":   ["INFO claude stream event received"]
      }
    },
    {
      "id": "pm_no_snapshot_404",
      "title": "PM sin snapshot (404 esperado)",
      "class": "expected-empty-state",
      "status": "by_design",
      "log_pattern": "\"error\"\\s*:\\s*\"NO_SNAPSHOT\"",
      "log_guarded": false,
      "killed_by": "no aplica — 404 by-design (estado vacio esperado)",
      "killed_commit": null,
      "date_resolved": null,
      "guard_test": "tests/test_pm_endpoints.py",
      "evidence": "backend/api/pm.py:303-308; frontend/src/pages/PMCommandCenter.tsx:866-868",
      "self_test": {
        "matches": ["{\"error\": \"NO_SNAPSHOT\"}"],
        "clean":   ["{\"snapshots\": []}"]
      }
    }
  ]
}
```

- **Convención de estados:** `resolved` (matada — el smoke alarma si reaparece), `open` (conocida sin fix — documentada, no guardada), `by_design` (comportamiento esperado — nunca guardada).
- **`log_guarded`:** sólo las huellas `resolved` **Y** `log_guarded: true` las grepa el smoke de F5 (hoy: `pipeline_status_404` y `ansi_in_file_log`, las dos de la tesis). Las demás `resolved` se guardan por su `guard_test` (pytest), no por el log.
- **`killed_by` por número vs nombre:** los planes YA implementados (145/148/149/144/135/37) se citan por número+commit (son históricos, estables, trazables). Los planes **hermanos del roadmap actual** (ledger de publicación, arnés veraz, latido único) se citan por **nombre** (sus números pueden moverse).

**Paso 2 — Test** `backend/tests/test_error_fingerprints_catalog.py`:

| Test | Qué afirma |
|---|---|
| `test_json_valido` | El archivo existe y `json.loads` no lanza; `schema_version == 1`; `fingerprints` es lista no vacía. |
| `test_campos_obligatorios` | Cada entrada tiene `id`, `title`, `class`, `status`, `log_pattern`, `log_guarded`, `killed_by`, `guard_test`, `self_test`. |
| `test_sin_ids_duplicados` | El set de `id` tiene el mismo largo que la lista (no hay duplicados). |
| `test_status_enum` | Cada `status` ∈ `{"resolved","open","by_design"}`. |
| `test_patrones_compilan` | `re.compile(fp["log_pattern"])` no lanza para todas las entradas. |
| `test_self_test_coherente` | Para cada entrada: cada muestra de `self_test.matches` matchea `log_pattern`, y cada `self_test.clean` **no** matchea. |
| `test_ruta_canonica` | El archivo está en `docs/sistema/error_fingerprints.json` y su extensión es `.json` (no `.md`). |

(Localizar el catálogo desde el test: `backend_root().parent / "docs" / "sistema" / "error_fingerprints.json"`.)

**Paso 3 — Ítem en la skill.** En `.claude/skills/criticar-y-mejorar-plan/SKILL.md`, en el checklist de red-team (bloque `:66-84`), agregar UN bullet después del ítem de "Casos borde y riesgos" (`:84`), como **convención** (no gate duro):

```
- [ ] Huella de regresión (planes tipo-fix): si el plan MATA una clase de error, ¿registra su huella en `Stacky Agents/docs/sistema/error_fingerprints.json` (id, patrón, plan/commit, fecha, guard_test)? Es convención, no bloqueante: marcá su ausencia como MENOR.
```

**Paso 4 — Registrar** `tests/test_error_fingerprints_catalog.py` en el bloque Plan 156 de `run_harness_tests.sh` y `.ps1`.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_catalog.py -q` → exit 0; el catálogo es `.json` bajo `docs/sistema/`; `grep -c "test_error_fingerprints_catalog.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`; `grep -c "error_fingerprints.json" .claude/skills/criticar-y-mejorar-plan/SKILL.md` → `≥ 1`.

**Flag:** ninguna. **Runtimes:** catálogo de datos + convención de skill; agnóstico de runtime. **Trabajo del operador: ninguno.**

---

### F5 — Scanner de huellas + smoke NEGATIVO sobre los logs frescos del deploy

**Objetivo (1 frase):** un scanner Python (fuente única de la lógica de grep, sustrato del futuro plan de análisis de logs) + un smoke de PowerShell que FALLA si una clase de error `resolved`+`log_guarded` reaparece en un log fresco. **Valor:** un deploy que reintroduce el 404 de pipeline/status o el ANSI en logs **falla el smoke** en vez de correr todo el día en silencio.

**Archivos:**
- NUEVO `backend/services/error_fingerprints.py` (loader + `scan_text`)
- NUEVO `deployment/smoke_fingerprints.ps1` (smoke NEGATIVO, PS 5.1)
- NUEVO `backend/tests/test_error_fingerprints_scan.py`
- MODIFICADO `backend/scripts/run_harness_tests.sh` y `.ps1` (registrar el test)

**Paso 1 — `backend/services/error_fingerprints.py` (fuente única de la lógica de scan):**

```python
"""Plan 156 F5 — loader + scanner del catalogo de huellas de regresion.

Fuente UNICA de la logica de grep (el smoke de PowerShell consume el MISMO
catalogo). Sustrato del futuro plan de analisis local de logs con clustering."""
from __future__ import annotations

import json
import re
from pathlib import Path
from runtime_paths import backend_root


def catalog_path() -> Path:
    return backend_root().parent / "docs" / "sistema" / "error_fingerprints.json"


def load_fingerprints() -> list[dict]:
    data = json.loads(catalog_path().read_text(encoding="utf-8"))
    return data.get("fingerprints", [])


def guarded_fingerprints(fingerprints: list[dict] | None = None) -> list[dict]:
    """Solo las huellas que el smoke NEGATIVO debe alarmar: resolved + log_guarded."""
    fps = fingerprints if fingerprints is not None else load_fingerprints()
    return [fp for fp in fps if fp.get("status") == "resolved" and fp.get("log_guarded") is True]


def scan_text(text: str, fingerprints: list[dict] | None = None) -> list[str]:
    """Devuelve los ids de huellas GUARDADAS cuyo patron aparece en el texto."""
    hits: list[str] = []
    for fp in guarded_fingerprints(fingerprints):
        if re.search(fp["log_pattern"], text):
            hits.append(fp["id"])
    return hits
```

**Paso 2 — `deployment/smoke_fingerprints.ps1` (PS 5.1; sin `&&`, sin ternarios, sin here-strings indentados):**

```powershell
#Requires -Version 5.1
<#
.SYNOPSIS
    Smoke NEGATIVO de huellas de regresion (Plan 156 F5).
.DESCRIPTION
    Lee docs/sistema/error_fingerprints.json y, por cada huella resolved+log_guarded,
    grepea el log objetivo. Si ENCUENTRA alguna, FALLA (exit 1): una clase de error
    ya resuelta reaparecio. Corre desde el repo; -LogPath apunta al log fresco del deploy.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [string]$CatalogPath = (Join-Path $PSScriptRoot "..\docs\sistema\error_fingerprints.json")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $LogPath)) { throw "No existe el log objetivo: $LogPath" }
if (-not (Test-Path $CatalogPath)) { throw "No existe el catalogo: $CatalogPath" }

$catalog = Get-Content -Raw -Path $CatalogPath | ConvertFrom-Json
$guarded = $catalog.fingerprints | Where-Object { $_.status -eq "resolved" -and $_.log_guarded -eq $true }

$found = @()
foreach ($fp in $guarded) {
    $hit = Select-String -Path $LogPath -Pattern $fp.log_pattern -List -ErrorAction SilentlyContinue
    if ($null -ne $hit) {
        $found += $fp
        Write-Host ("[REGRESION] {0} ({1}) — matada por {2}" -f $fp.id, $fp.title, $fp.killed_by) -ForegroundColor Red
    }
}

if ($found.Count -gt 0) {
    Write-Host ("Smoke de huellas FALLO: {0} clase(s) de error resuelta(s) reaparecieron en {1}" -f $found.Count, $LogPath) -ForegroundColor Red
    exit 1
}

Write-Host ("Smoke de huellas OK: ninguna clase resuelta reaparecio en {0}" -f $LogPath) -ForegroundColor Green
exit 0
```

- **Por qué repo-side y no bundle:** el smoke corre desde el repo (donde vive `docs/sistema/`), leyendo `-LogPath` (que apunta al log fresco del deploy: `<app_root>/data/logs/stacky-<fecha>.log`). Así **NO** hay que tocar `build_release.ps1` para bundlear el catálogo (respeta "no tocar el build"). El pipeline (que corre desde el repo tras un deploy) lo invoca.
- **Nota sobre el smoke fresco del release** (`release_assets/smoke_test.ps1`): arranca el exe con **DB y data dir frescos** (`data\smoke`) — su log fresco no reproduce el tráfico histórico. Por eso el smoke de huellas apunta preferentemente al **log real del deploy** vía `-LogPath`, no al log del smoke fresco. Ese smoke fresco NO se modifica (se lo deja intacto).

**Paso 3 — Test** `backend/tests/test_error_fingerprints_scan.py`:

| Test | Qué afirma |
|---|---|
| `test_scan_log_sucio` | `scan_text` sobre un texto que contiene la muestra `self_test.matches[0]` de `pipeline_status_404` → devuelve `["pipeline_status_404"]`. |
| `test_scan_log_limpio` | `scan_text` sobre un texto armado con las muestras `self_test.clean` de las huellas guardadas → `[]`. |
| `test_scan_ansi` | `scan_text` sobre un texto con un ESC ANSI real (`"\x1b[32mx\x1b[0m"`) → contiene `"ansi_in_file_log"`. |
| `test_solo_guardadas` | `guarded_fingerprints()` devuelve sólo entradas `resolved` + `log_guarded`; NO incluye `ado_workitem_type_vs402323` (open) ni `pm_no_snapshot_404` (by_design). |
| `test_scan_multiple` | `scan_text` sobre un texto que concatena las muestras "match" de TODAS las guardadas → devuelve todos sus ids (grep NEGATIVO detecta cada regresión). |

**Paso 4 — Registrar** `tests/test_error_fingerprints_scan.py` en el bloque Plan 156 de `run_harness_tests.sh` y `.ps1`.

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_error_fingerprints_scan.py -q` → exit 0; `grep -c "test_error_fingerprints_scan.py" scripts/run_harness_tests.sh` → `1` e ídem `.ps1` → `1`. **Verificación manual (documentada):** crear un log de fixture con la línea `"GET /api/v1/pipeline/status HTTP/1.1" 404 -` → `pwsh -File deployment/smoke_fingerprints.ps1 -LogPath <fixture>` → exit 1; un log limpio → exit 0.

**Flag:** ninguna. **Runtimes:** scanner + smoke sobre logs del backend; agnóstico del runtime de agentes. **Fallback:** si el catálogo o el log faltan, el smoke lanza con mensaje claro (no falso verde). **Trabajo del operador: ninguno** (el pipeline invoca el smoke).

---

## 6. Orden de implementación (numerado)

1. **F1** — `app_version.py` (`source_commit`/`built_at`/`repo_head`/`build_drift`) + campos en `/api/diag/health` + test + registro en el arnés.
2. **F2** — ampliar el tipo de `Health.get` + helpers puros `buildIdentity.ts` + chip/banner en TopBar + CSS + test. Corre después de F1 (consume los campos nuevos).
3. **F3** — `lifecycle_log.py` + wiring en `create_app()` + test + registro. Independiente de F1/F2.
4. **F4** — catálogo `docs/sistema/error_fingerprints.json` + schema-test + ítem en la skill + registro.
5. **F5** — `services/error_fingerprints.py` + `deployment/smoke_fingerprints.ps1` + scan-test + registro. Corre después de F4 (consume el catálogo).

Correr `npx tsc --noEmit` al terminar F2. Cada test SIEMPRE por archivo con el venv real del checkout principal.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Un `kill -9` / corte de energía no dispara el evento de shutdown. | **Aceptado y documentado** (principio 7): es física, no un bug. F3 captura apagados gráciles (atexit/SIGTERM/SIGINT). La ausencia de un `shutdown` seguido de un `startup` nuevo es, de hecho, la evidencia del corte abrupto (justo el caso L8). |
| R2 | En Windows, `signal.SIGTERM` es limitado y `taskkill /F` no lo dispara. | El handler es **best-effort** dentro de un `try/except (ValueError, OSError)`; atexit cubre el apagado normal y `SystemExit`. No se promete cobertura total; se promete no romper. |
| R3 | Llamar git en `get_repo_head` degrada performance si es por request. | TTL de 10 s (`_REPO_HEAD_TTL_SECONDS`): una ráfaga de requests comparte una sola llamada. `source_commit`/`built_at` se cachean a nivel módulo (una sola vez). En deploy, `get_repo_head` retorna `None` sin tocar git (frozen o manifest presente). |
| R4 | El manifest no tiene `built_at` y alguien "arregla" el build para agregarlo. | Este plan LEE `generated_at` (drift corregido en §2.2). **NO** se toca `build_release.ps1`. Documentado en glosario y fuera de scope. |
| R5 | El catálogo `.md` contaminaría el DocTree del `doc_indexer`. | Es **`.json`** bajo `docs/sistema/`; `doc_indexer` sólo escanea `*.md` (`:270`). `test_error_fingerprints_catalog.py::test_ruta_canonica` lo fija. |
| R6 | El smoke de huellas da falso verde porque el log fresco del release no tiene tráfico. | El smoke apunta al **log real del deploy** vía `-LogPath` (`data/logs/stacky-*.log`), no al log del smoke fresco. El scan-test (pytest) es el gate binario determinista; el smoke PS es el brazo de deploy. |
| R7 | Los `self_test.matches` del catálogo o los tests contienen los patrones y podrían auto-matchearse. | El smoke grepa **`-LogPath`** (logs), nunca el repo ni este plan ni el catálogo. Los patrones en el catálogo/tests son su función, no un log. Ver §9. |
| R8 | Divergencia entre el regex de Python (`re`) y el de .NET (`Select-String`). | Los patrones se mantienen en un subconjunto común (clases de caracteres, cuantificadores, `\S`, `\d`, `\x1b`). `test_patrones_compilan` valida Python; la verificación manual de F5 valida .NET. Sin construcciones exclusivas de un motor. |
| R9 | Reset de cachés de módulo entre tests deja estado sucio. | Un `pytest.fixture(autouse=True)` en `test_app_version_build_identity.py` resetea las 5 cachés antes de cada test (documentado en F1 Paso 3). |

---

## 8. Fuera de scope (explícito)

- **El plan diferido de "análisis local de logs con clustering".** F4/F5 dejan el catálogo + el scanner como **sustrato**; el análisis semántico/clustering de logs es otro plan (al final de la cola). Este plan sólo hace grep determinista de patrones conocidos.
- **Cualquier auto-reinicio del server.** El drift AVISA; el operador decide. Nada se reinicia solo (human-in-the-loop).
- **Tocar el pipeline de build más allá de LEER el manifest.** No se agrega ningún campo a `release-manifest.json` (se reusa `generated_at`), no se bundlea nada nuevo, no se modifica `build_release.ps1`.
- **Modificar el smoke fresco del release** (`release_assets/smoke_test.ps1`). Se lo deja intacto; F5 agrega un smoke **separado** (`smoke_fingerprints.ps1`).
- **Guardar por log las huellas `open`/`by_design`.** VS402323 (open) y NO_SNAPSHOT (by_design) se documentan en el catálogo pero **no** hacen fallar el smoke.
- **Resolver VS402323.** Su fix es el plan del ledger de publicación transaccional, no éste.
- **Tests de render (`render()`/RTL).** No hay `@testing-library/react` ni `jsdom` en `frontend/package.json`; todo test de frontend es de lógica pura + `tsc`.
- **Panel/UI de gestión del catálogo.** El catálogo se edita como archivo `.json` versionado; no hay editor en la UI (mono-operador, cero config nueva).

---

## 9. Advertencias para el implementador (leer antes de tocar nada)

- **El catálogo DEBE ser `.json`, jamás `.md`.** `doc_indexer` escanea `docs/**/*.md`; un `.md` contaminaría el corpus RAG. `test_ruta_canonica` lo fija.
- **PowerShell 5.1 en `smoke_fingerprints.ps1`:** sin `&&` encadenado, sin ternarios, sin null-coalescing, sin here-strings `@'...'@` indentados. Usar `if/else`, `Select-String`, `ConvertFrom-Json`. El cierre de un here-string (si se usara) va en columna 0.
- **Cachear git a nivel módulo, JAMÁS por request** (perf): `source_commit`/`built_at` una sola vez; `repo_head` con TTL de 10 s (única concesión, justificada porque el drift es un blanco móvil; ver R3). En deploy, `get_repo_head` ni siquiera llama git.
- **`built_at` sale de `generated_at`** del manifest (el manifest NO tiene `built_at`). NO agregar campos al build.
- **RTL/jsdom NO están en `frontend/package.json`.** Prohibido `render()`/`renderHook`. El test del chip es de **lógica pura** (`buildIdentity.ts`) + `tsc --noEmit`. El banner de drift se verifica por smoke manual.
- **`.tsx` y el uiDebtRatchet:** el TopBar ya existe; NO introducir `style={{}}` inline nuevos (usar clases de `TopBar.module.css` con tokens de `theme.css`). El plan hermano del latido único puede haber sumado un ratchet de diálogos nativos: **no** agregar `confirm/alert/prompt` nuevos en el TopBar.
- **Tests backend nuevos van registrados** en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` **Y** su `.ps1`, o el meta-test ratchet cae. Formato: sh `  tests/<archivo>.py` bajo `# — Plan 156 · ... —`; ps1 `  "tests/<archivo>.py"` bajo `# Plan 156 - ...`.
- **Gotcha comentario-choca-con-gate (recurrido 6+ veces):** este plan **no** introduce ningún grep-gate sobre código/prosa (el smoke grepa **logs**). Aun así, no escribir en comentarios de código literales de log que un futuro gate pudiera cazar; los patrones viven sólo en el catálogo `.json` y en los `self_test`.
- **venv backend real:** `backend\.venv\Scripts\python.exe` (py3.13). El `.venv` del worktree `C:/wt/uxlog` puede no existir → correr los tests en el checkout principal `N:\GIT\RS\STACKY\Stacky`.
- **Escribir a SQLAlchemy en atexit** es seguro **sólo desde el main thread** (patrón de `stacky_logger._flush_on_exit`). `log_shutdown` abre su propio `session_scope` síncrono; NO delegar a un thread daemon (gotcha crash nativo daemon vs teardown).
- **Sesión concurrente en el mismo árbol:** `git status -- "<ruta>"` antes de cada fase caliente; staging quirúrgico por path; el implementador NO commitea.

---

## 10. Definition of Done (global)

- [ ] KPI-1..KPI-8 en verde con los comandos exactos de §1, cada test corrido por archivo con el venv real y su salida pegada en el resumen.
- [ ] `GET /api/diag/health` expone `source_commit`, `built_at`, `repo_head` y `build_drift`; en deploy `repo_head`/`build_drift` son `null`/`false`; en dev reflejan el estado real.
- [ ] El chip del TopBar muestra `v<version> · <short-hash>` con tooltip de `built_at`; el banner de drift aparece SÓLO en dev cuando el proceso corre código anterior al repo, y AVISA sin reiniciar.
- [ ] Un apagado grácil del backend deja UNA fila `system_logs` con `source="app_lifecycle"`, `action="shutdown"` y el motivo en `context_json`.
- [ ] `docs/sistema/error_fingerprints.json` existe (`.json`), con las 8 clases ancladas, schema-test verde; la skill `criticar-y-mejorar-plan` tiene el ítem de convención.
- [ ] `services/error_fingerprints.py::scan_text` detecta las huellas `resolved`+`log_guarded` y NO las `open`/`by_design`; `smoke_fingerprints.ps1` falla (exit 1) ante una regresión y pasa (exit 0) con log limpio (demostrado con fixture).
- [ ] `npx tsc --noEmit` verde; los 4 tests backend nuevos registrados en `run_harness_tests.sh` Y `.ps1`.
- [ ] Sin flags nuevas, sin config nueva, backward-compatible: campos opcionales, chip/banner automáticos, catálogo poblado, smoke invocado por el pipeline. "Trabajo del operador: ninguno" se cumple.
- [ ] Pre-flight `git status` por archivo caliente hecho; sin WIP ajeno arrastrado; el implementador NO commiteó.
- [ ] `build_release.ps1` NO fue modificado (se respetó "no tocar el build más allá de leer el manifest").
